import tempfile
import unittest
from pathlib import Path
from statistics import mean, pstdev

from living_world.blacksmith import FORGE_INPUTS, FORGE_MINUTES
from living_world.craftsmanship import quality
from living_world.model import ANVIL, COIN, FARM_OWNER, FIREWOOD, GRAIN, IRON, IRON_HOE, Config, ForgeIntent, WorldError
from living_world.persistence import Save
from living_world.player import execute
from living_world.routes import BLACKSMITH, MARKET_SQUARE, stall


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def create(self, name, *, player_name="Iara", config=None):
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="hamlet",
                           player_name=player_name)

    def test_character_requires_a_hamlet_and_a_printable_name(self):
        with self.assertRaisesRegex(WorldError, "hamlet or civilian scenario"):
            Save.create(self.directory / "lab.db", 8, player_name="Iara")
        self.assertFalse((self.directory / "lab.db").exists())
        for name in ("  ", "A\nB", "A" * 33):
            with self.subTest(name=name), self.assertRaisesRegex(WorldError, "printable characters"):
                self.create("invalid", player_name=name)
        self.assertFalse((self.directory / "invalid.db").exists())

    def test_an_idle_player_leaves_npc_decisions_and_balances_unchanged(self):
        idle = self.create("idle")
        control = self.create("control", player_name=None)
        for save in (idle, control):
            save.advance(days=1)
        idle_state = idle.inspect(journal=True)
        control_state = control.inspect(journal=True)
        player = idle_state["snapshot"]["player_id"]
        self.assertEqual(idle_state["journal"][1:], control_state["journal"][1:])
        self.assertEqual(idle_state["snapshot"]["inventory"].pop(player), {COIN: 3, GRAIN: 0})
        self.assertEqual(idle_state["snapshot"]["inventory"], control_state["snapshot"]["inventory"])
        self.assertNotIn("player_id", control_state["snapshot"])
        idle.audit_inventory()

    def test_character_works_travels_buys_eats_and_reopens_the_same_save(self):
        save = self.create("civilian")
        self.assertIn("Iara is at east-farm", execute(save, "look"))
        self.assertIn("Earned 2 coin", execute(save, "work"))
        self.assertIn("after 20 minutes", execute(save, "go market-square"))
        self.assertIn("farm-owner: 3 grain at 1 coin", execute(save, "market"))
        self.assertIn("Bought one grain from farm-owner for 1 coin", execute(save, "buy farm-owner"))
        self.assertIn("Ate one grain", execute(save, "eat"))
        self.assertIn("Rested", execute(save, "rest"))

        save = Save(save.path)
        self.assertIn("coin: 4, grain: 0", execute(save, "inventory"))
        self.assertIn("Fatigue: 0", execute(save, "inventory"))
        report = save.inspect(journal=True)
        player = report["snapshot"]["player_id"]
        self.assertEqual(report["snapshot"]["actors"][player]["location"], MARKET_SQUARE)
        purchase = next(event for event in report["journal"]
                        if event["kind"] == "buy_food_completed" and event["payload"]["actor"] == player)
        self.assertEqual(purchase["payload"]["movements"][-1],
                         {"source": player, "destination": FARM_OWNER, "good": COIN, "quantity": 1})
        action_start = report["journal"][purchase["cause_id"] - 1]
        self.assertEqual(report["journal"][action_start["cause_id"] - 1]["kind"], "player_command")
        self.assertFalse(any(event["kind"] == "decision_waited" and event["payload"]["actor"] == player
                             for event in report["journal"]))
        save.audit_inventory()

    def test_invalid_actions_do_not_advance_time_or_commit_events(self):
        save = self.create("poor", config=Config.from_mapping({"village": {"starting_hand_coin": 0}}))
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "visit market-square"):
            execute(save, "buy")
        with self.assertRaisesRegex(WorldError, "no direct road"):
            execute(save, "go west-farm")
        with self.assertRaisesRegex(WorldError, "insufficient available grain"):
            execute(save, "eat")
        self.assertEqual(save.inspect(journal=True), before)

        execute(save, "go market-square")
        execute(save, "wait 60")
        self.assertIn("grain", execute(save, "market"))
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "insufficient available coin"):
            execute(save, "buy")
        self.assertEqual(save.inspect(journal=True), before)

    def test_civilian_and_npc_both_learn_from_a_paid_forge_shift(self):
        control = Save.create(self.directory / "control-civilian.db", 8, scenario="civilian")
        player = Save.create(self.directory / "apprentice.db", 8, scenario="civilian", player_name="Iara")
        execute(player, "go market-square")
        execute(player, "go forge")
        execute(player, "wait 1033")
        self.assertIn("0 XP", execute(player, "skills"))
        self.assertIn("Earned 2 coin and 1 blacksmithing XP", execute(player, "work"))
        control.advance(days=7)
        for save, worker in ((Save(player.path), "player"), (control, "farmhand-21")):
            report = save.inspect(journal=True)
            match = next(event for event in report["journal"]
                         if event["kind"] == "forge_hoe_completed" and event["payload"]["actor"] == worker)
            self.assertEqual(match["payload"]["blacksmithing_xp"], 1)
            self.assertEqual(match["payload"]["movements"][0],
                             {"source": FORGE_INPUTS, "destination": None, "good": IRON, "quantity": 1})
            self.assertEqual(match["payload"]["movements"][-1]["quantity"], 2)
            self.assertIn({"source": FORGE_INPUTS, "destination": None, "good": FIREWOOD, "quantity": 1},
                          match["payload"]["movements"])
            item = match["payload"]["crafted_hoes"][0]
            self.assertEqual(item["maker"], worker)
            self.assertEqual(item["iron_source"], FORGE_INPUTS)
            self.assertEqual(item["fuel_source"], FORGE_INPUTS)
            self.assertEqual(report["snapshot"]["blacksmithing_xp"][worker], 1)
            save.audit_inventory()

    def test_canceling_a_forge_shift_releases_iron_without_training(self):
        save = Save.create(self.directory / "canceled-forge.db", 8, scenario="civilian", player_name="Iara")
        execute(save, "go market-square")
        execute(save, "go forge")
        execute(save, "wait 1033")
        save.submit("apprentice", ForgeIntent("forge_hoe", "player", FORGE_MINUTES))
        self.assertEqual(save.read(lambda sim: sim.available(FORGE_INPUTS, IRON)), 0)
        save.cancel("apprentice")
        self.assertEqual(save.read(lambda sim: sim.available(FORGE_INPUTS, IRON)), 1)
        self.assertIn("0 XP", execute(save, "skills"))
        self.assertIn("coin: 3", execute(save, "inventory"))

    def test_forge_checks_for_its_anvil_and_fuel(self):
        save = Save.create(self.directory / "missing-tools.db", 8, scenario="civilian", player_name="Iara")
        execute(save, "go market-square")
        execute(save, "go forge")
        execute(save, "wait 1033")
        save.mutate(lambda sim: sim.world.inventory[FORGE_INPUTS].update({ANVIL: 0}))
        with self.assertRaisesRegex(WorldError, "requires an anvil"):
            execute(save, "work")
        save.mutate(lambda sim: sim.world.inventory[FORGE_INPUTS].update({ANVIL: 1, FIREWOOD: 0}))
        with self.assertRaisesRegex(WorldError, "insufficient available firewood"):
            execute(save, "work")
        self.assertIn("0 XP", execute(save, "skills"))
        self.assertIn("coin: 3", execute(save, "inventory"))

    def test_higher_skill_increases_mean_quality_and_reduces_variation(self):
        novice = [quality(seed, 1, 0, 0, 4) for seed in range(400)]
        expert = [quality(seed, 1, 5, 0, 4) for seed in range(400)]
        self.assertGreater(mean(expert), mean(novice))
        self.assertLess(pstdev(expert), pstdev(novice))
        self.assertGreater(max(novice), min(expert))

    def test_civilian_buys_supplies_rents_the_forge_and_sells_the_same_hoe(self):
        save = Save.create(self.directory / "smith.db", 8, scenario="civilian", player_name="Iara")
        for command in (
            "work", "work", "rest", "work", "wait 120", "work", "rest", "work", "work", "rest",
            "go market-square", "wait 720", "buy iron", "buy firewood", "go forge", "craft hoe",
        ):
            execute(save, command)

        before = save.inspect()["snapshot"]
        player_hoe, record = next((item, hoe) for item, hoe in before["crafted_hoes"].items()
                                  if hoe["account"] == "player")
        self.assertEqual(record["maker"], "player")
        self.assertEqual(record["iron_source"], "player")
        self.assertEqual(before["inventory"]["player"][COIN], 0)
        self.assertEqual(before["inventory"]["player"][IRON], 0)
        self.assertEqual(before["inventory"]["player"][FIREWOOD], 0)

        save = Save(save.path)
        execute(save, "go market-square")
        execute(save, "sell hoe")
        after = save.inspect()["snapshot"]
        self.assertEqual(after["inventory"]["player"][COIN], 16)
        self.assertEqual(after["inventory"]["player"][IRON_HOE], 0)
        self.assertEqual(after["crafted_hoes"][player_hoe], record | {"account": stall(BLACKSMITH)})
        save.audit_inventory()
