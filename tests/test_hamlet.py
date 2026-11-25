import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from living_world.blacksmith import FORGE_INPUTS, FORGE_MINUTES
from living_world.model import COIN, FARM_OWNER, GRAIN, IRON, IRON_HOE, Config, ForgeIntent, MarketIntent, WorldError
from living_world.persistence import Save
from living_world.routes import BLACKSMITH, FIELDS, FORGE, MARKET_SQUARE, TOOL_STOCK, WEST_FARM, stall


class HamletTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def create(self, name, config=None, seed=8):
        return Save.create(self.directory / f"{name}.db", seed, config or Config(), scenario="hamlet")

    def test_population_uses_unique_names_and_leaves_small_village_unchanged(self):
        actors = self.create("hamlet").inspect()["snapshot"]["actors"]
        farmhands = [actor for key, actor in actors.items() if key.startswith("farmhand-")]
        self.assertEqual(len(actors), 31)
        self.assertEqual(len(farmhands), 24)
        self.assertEqual(len({actor["name"] for actor in farmhands}), 24)
        small = Save.create(self.directory / "small.db", 8, Config(), scenario="seed-trade")
        small_actors = small.inspect()["snapshot"]["actors"]
        self.assertEqual(sum(key.startswith("farmhand-") for key in small_actors), 2)
        self.assertNotIn("hamlet", small.inspect()["snapshot"]["config"])

    def test_configuration_is_validated(self):
        with self.assertRaisesRegex(WorldError, "hamlet.farmhands"):
            Config.from_mapping({"hamlet": {"farmhands": 41}})
        with self.assertRaisesRegex(WorldError, "unknown configuration fields: crews"):
            Config.from_mapping({"hamlet": {"crews": 2}})
        with self.assertRaisesRegex(WorldError, "hamlet.hired_shifts_per_farm"):
            Config.from_mapping({"hamlet": {"hired_shifts_per_farm": 0}})
        with self.assertRaisesRegex(WorldError, "hamlet.farms"):
            Config.from_mapping({"hamlet": {"farms": 7}})

    def test_additional_farms_publish_real_grain_and_reconcile_in_the_journal(self):
        config = Config.from_mapping({"hamlet": {"farms": 4}})
        save = self.create("four-farms", config)
        save.advance(days=7)
        summary = save.summary()
        village = summary["village"]
        self.assertEqual(summary["actors"], 33)
        self.assertEqual(village["coin_supply"], 258)
        self.assertEqual(len(village["travel"]["roads_to_market"]) + 1, 10)
        for farm in ("north-farm-owner", "south-farm-owner"):
            self.assertGreater(village["market"]["harvests_by_farm"][farm], 0)
            self.assertGreater(village["market"]["purchases_by_seller"][farm], 0)
        save.audit_inventory()

    def test_farm_hires_up_to_its_shift_limit_and_reopens_after_cancellation(self):
        config = Config.from_mapping({"hamlet": {"farmhands": 4, "hired_shifts_per_farm": 3}})
        save = self.create("shifts", config)
        hands = [f"farmhand-{index}" for index in range(1, 5)]

        def stage(sim):
            sim.world.queue.clear()
            for hand in hands:
                sim.world.actors[hand] = replace(sim.world.actors[hand], location=FIELDS[FARM_OWNER])

        save.mutate(stage)
        shift = lambda hand: MarketIntent("harvest", hand, config.village.harvest_minutes, FARM_OWNER)
        for hand in hands[:3]:
            save.submit(hand, shift(hand))
        with self.assertRaisesRegex(WorldError, "hired field shift is occupied"):
            save.submit(hands[3], shift(hands[3]))
        save.cancel(hands[0])
        save.submit(hands[3], shift(hands[3]))
        save.advance(minutes=config.village.harvest_minutes)
        summary = save.summary()
        self.assertEqual(summary["village"]["coin_paid_in_wages"], 3 * config.village.wage)
        self.assertEqual(summary["inventory"][FARM_OWNER][COIN],
                         config.village.starting_owner_coin - 3 * config.village.wage)

    def test_woodcutter_takes_field_shifts_after_the_woodland_is_exhausted(self):
        save = self.create("no-wood", Config(starting_standing_wood=0))
        save.advance(days=2)
        journal = save.inspect(journal=True)["journal"]
        shifts = [event for event in journal if event["kind"] == "harvest_completed"
                  and event["payload"].get("actor") == "woodcutter"]
        self.assertTrue(shifts)
        self.assertFalse(any(event["kind"] == "cut_wood_completed" for event in journal))
        self.assertGreater(save.summary()["village"]["coin_paid_in_wages"], 0)

    def test_last_grain_at_a_stall_goes_to_exactly_one_of_two_buyers(self):
        save = self.create("last-grain")

        def stage(sim):
            sim.world.queue.clear()
            sim.world.inventory[stall(FARM_OWNER)][GRAIN] = 1
            sim.world.inventory[stall(WEST_FARM)][GRAIN] = 0
            for hand in ("farmhand-1", "farmhand-2"):
                sim.world.actors[hand] = replace(sim.world.actors[hand], location=MARKET_SQUARE)

        save.mutate(stage)
        price = save.summary()["village"]["market"]["offers"][0]["price"]
        first = MarketIntent("buy_food", "farmhand-1", Config().village.purchase_minutes, FARM_OWNER, price)
        save.submit("first", first)
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "no grain offered"):
            save.submit("second", replace(first, actor="farmhand-2"))
        self.assertEqual(save.inspect(journal=True), before)
        save.advance(minutes=Config().village.purchase_minutes)
        summary = save.summary()
        self.assertEqual(summary["village"]["purchases"], 1)
        self.assertEqual(summary["inventory"]["farmhand-1"][GRAIN], 1)
        self.assertEqual(summary["inventory"]["farmhand-2"][GRAIN], 0)
        self.assertEqual(summary["village"]["coin_supply"], 222)

    def test_saved_continuation_matches_direct_run_and_conserves_coins(self):
        direct = self.create("direct")
        direct.advance(days=1)
        split = self.create("split")
        split.advance(minutes=700)
        split = Save(split.path)
        split.advance_to(1440)
        observed = direct.inspect(journal=True)
        self.assertEqual(Save(split.path).inspect(journal=True), observed)
        village = direct.summary()["village"]
        self.assertEqual(village["coin_supply"], 222)
        self.assertEqual(village["failed_actions"], 0)
        self.assertGreater(village["harvests"], 0)
        self.assertGreater(village["purchases"], 0)

    def test_forge_hires_only_when_it_can_reserve_wages_and_iron(self):
        save = self.create("forge")
        wage = Config().village.wage
        action = ForgeIntent("forge_hoe", "farmhand-1", FORGE_MINUTES)
        with self.assertRaisesRegex(WorldError, "eligible worker at the forge"):
            save.submit("remote", action)

        def stage(sim):
            world = sim.world
            world.queue.clear()
            for actor in ("farmhand-1", "farmhand-2"):
                world.actors[actor] = replace(world.actors[actor], location=FORGE)
            world.inventory[FORGE_INPUTS][IRON] = 2
            world.inventory[BLACKSMITH][COIN] = wage - 1

        save.mutate(stage)
        with self.assertRaisesRegex(WorldError, "insufficient available coin"):
            save.submit("unfunded", action)
        save.mutate(lambda sim: sim.world.inventory[BLACKSMITH].update({COIN: wage}))
        save.submit("first", action)
        with self.assertRaisesRegex(WorldError, "forge shift is occupied"):
            save.submit("second", replace(action, actor="farmhand-2"))
        save.market_shock("worker-loss")
        save.submit("second", replace(action, actor="farmhand-2"))
        Save(save.path).advance(minutes=FORGE_MINUTES)
        report = save.summary()
        self.assertEqual(report["inventory"][FORGE_INPUTS][IRON], 1)
        self.assertEqual(report["inventory"][TOOL_STOCK][IRON_HOE], 1)
        self.assertEqual(report["inventory"][BLACKSMITH][COIN], 0)
        self.assertEqual(report["inventory"]["farmhand-2"][COIN], Config().village.starting_hand_coin + wage)
        self.assertEqual(report["village"]["employment"]["coin_paid_in_forge_wages"], wage)

    def test_farmhands_take_forge_shifts_and_craft_workers_take_field_shifts(self):
        save = self.create("switch")
        save.advance(days=7)
        village = save.summary()["village"]
        self.assertGreater(village["employment"]["hired_forge_shifts"], 0)
        self.assertGreater(village["employment"]["craft_workers_field_shifts"][BLACKSMITH], 0)
        self.assertEqual(village["coin_supply"], 222)


if __name__ == "__main__":
    unittest.main()
