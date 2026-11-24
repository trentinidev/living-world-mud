from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.model import CHARCOAL, COIN, IRON, IRON_ORE, Config, SmeltingIntent, VillageConfig, WorldError
from living_world.persistence import Save
from living_world.routes import CHARCOAL_BURNER, MARKET_SQUARE, MINER, SMELTER, stall
from living_world.simulation import Simulation
from living_world.smelting import BATCH_MINUTES, IRON_STOCK

BATCH = SmeltingIntent("smelt_iron", SMELTER, BATCH_MINUTES)


class SmeltingTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, config: Config | None = None) -> Save:
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="smelting")

    def test_batch_checks_both_inputs_and_rejects_a_shortfall_before_reserving(self) -> None:
        for good, stock in ((IRON_ORE, {CHARCOAL: 1}), (CHARCOAL, {IRON_ORE: 2})):
            with self.subTest(missing=good):
                save = self.create(good)
                save.mutate(lambda sim: sim.world.inventory[SMELTER].update(stock))
                before = save.inspect(journal=True)
                with self.assertRaisesRegex(WorldError, f"insufficient available {good}"):
                    save.submit("start", BATCH)
                self.assertEqual(save.inspect(journal=True), before)

    def test_industrial_purchases_reserve_stock_and_coins_and_pay_each_supplier(self) -> None:
        save = self.create("funds", Config(village=VillageConfig(
            farmhands=2, starting_hand_coin=5,
        )))

        def stock_market(sim: Simulation) -> None:
            world = sim.world
            world.actors[SMELTER] = replace(world.actors[SMELTER], location=MARKET_SQUARE)
            world.inventory[stall(MINER)][IRON_ORE] = 1
            world.inventory[stall(CHARCOAL_BURNER)][CHARCOAL] = 1
            world.inventory[SMELTER][COIN] = 7
            world.inventory["farmhand-1"][COIN] = 1
            world.queue.clear()

        save.mutate(stock_market)
        ore = SmeltingIntent("buy_iron_ore", SMELTER, 8, price=2)
        fuel = SmeltingIntent("buy_charcoal", SMELTER, 8, price=5)
        before = save.summary()["inventory"]
        with self.assertRaisesRegex(WorldError, "costs 2"):
            save.submit("wrong-price", replace(ore, price=1))
        with self.assertRaisesRegex(WorldError, "insufficient available coin"):
            save.submit("unfunded", replace(ore, actor="farmhand-1"))
        save.submit("ore", ore)
        save.advance_to(8)
        save.submit("charcoal", fuel)
        with self.assertRaisesRegex(WorldError, "insufficient available charcoal"):
            save.submit("last-charcoal", replace(fuel, actor="farmhand-2"))
        save.advance_to(16)
        inventory = save.summary()["inventory"]
        self.assertEqual(inventory[SMELTER][COIN], 0)
        self.assertEqual(inventory[MINER][COIN] - before[MINER][COIN], 2)
        self.assertEqual(inventory[CHARCOAL_BURNER][COIN] - before[CHARCOAL_BURNER][COIN], 5)
        self.assertEqual(inventory[SMELTER][IRON_ORE], 1)
        self.assertEqual(inventory[SMELTER][CHARCOAL], 1)
        self.assertEqual(inventory[stall(MINER)][IRON_ORE], 0)
        self.assertEqual(inventory[stall(CHARCOAL_BURNER)][CHARCOAL], 0)

    def test_charcoal_enters_the_market_only_on_delivery(self) -> None:
        complete = self.create("delivery")
        complete.advance_to(500)
        first = next(event for event in complete.inspect(journal=True)["journal"]
                     if event["kind"] == "travel_completed"
                     and any(move["good"] == CHARCOAL for move in event["payload"]["movements"]))
        en_route = self.create("en-route")
        en_route.advance_to(first["minute"] - 1)
        report = en_route.summary()["village"]
        self.assertEqual(report["travel"]["in_transit"][CHARCOAL_BURNER]["charcoal"], 1)
        self.assertEqual(report["smelting"]["charcoal_at_market"], 0)
        en_route.advance_to(first["minute"])
        self.assertEqual(en_route.summary()["village"]["smelting"]["charcoal_at_market"], 1)

    def test_cancel_and_retry_preserve_both_inputs_and_produce_iron_once(self) -> None:
        save = self.create("cancellation")
        save.advance_to(650)
        snapshot = save.inspect(journal=True)
        key = next(key for key, action in snapshot["snapshot"]["actions"].items()
                   if action["status"] == "started" and action["intent"].get("kind") == "smelt_iron")
        start = next(event for event in snapshot["journal"] if event["id"] ==
                     snapshot["snapshot"]["actions"][key]["start_event"])
        self.assertEqual(
            {move["good"]: move["quantity"] for move in start["payload"]["reservations"]},
            {IRON_ORE: 2, CHARCOAL: 1},
        )
        save.cancel(key)
        before = save.summary()["inventory"]
        self.assertEqual(before[SMELTER][IRON_ORE], 2)
        self.assertEqual(before[SMELTER][CHARCOAL], 1)
        self.assertEqual(before[IRON_STOCK][IRON], 0)
        save.submit("retry", BATCH)
        Save(save.path).advance(minutes=BATCH_MINUTES - 1)
        self.assertEqual(save.summary()["village"]["smelting"]["iron_in_stock"], 0)
        save.advance(minutes=1)
        self.assertEqual(save.submit("retry", BATCH).status, "completed")
        after = save.summary()["inventory"]
        self.assertEqual(after[SMELTER][IRON_ORE], 0)
        self.assertEqual(after[SMELTER][CHARCOAL], 0)
        self.assertEqual(after[IRON_STOCK][IRON], 1)

    def test_depleting_either_source_stops_iron_in_the_live_simulation(self) -> None:
        for config, purchased, absent in (
            (Config(starting_ore_deposit=0), "charcoal_purchased", "ore_purchased"),
            (Config(starting_standing_wood=0), "ore_purchased", "charcoal_purchased"),
        ):
            with self.subTest(missing=absent):
                save = self.create(absent, config)
                save.advance(days=7)
                village = save.summary()["village"]
                report = village["smelting"]
                self.assertGreater(report[purchased], 0)
                self.assertEqual(report[absent], 0)
                self.assertEqual(report["iron_produced"], 0)
                self.assertIsNone(report["batch_finishes_at"])
                self.assertEqual(village["coin_supply"], 114)

    def test_reload_mid_batch_matches_full_run_and_reconciles_every_account(self) -> None:
        direct, split = self.create("direct"), self.create("split")
        split.advance_to(650)
        pending = split.summary()["village"]["smelting"]
        self.assertEqual(pending["batch_finishes_at"], 754)
        self.assertEqual(pending["iron_in_stock"], 0)
        for save in (direct, Save(split.path)):
            save.advance_to(7 * 1440)
        self.assertEqual(direct.inspect(journal=True), split.inspect(journal=True))

        journal = split.inspect(journal=True)["journal"]
        stock = journal[0]["payload"]["inventory"]
        for event in journal[1:]:
            for move in event["payload"].get("movements", ()):
                good, quantity = move["good"], move["quantity"]
                if move["source"] is not None:
                    source = stock[move["source"]]
                    source[good] -= quantity
                    self.assertGreaterEqual(source[good], 0)
                if move["destination"] is not None:
                    target = stock[move["destination"]]
                    target[good] = target.get(good, 0) + quantity
        report = split.summary()
        self.assertEqual(report["inventory"], stock)
        self.assertEqual(report["village"]["coin_supply"], 114)
        self.assertEqual(stock[IRON_STOCK][IRON], 4)

    def test_cli_reports_iron_arrival_and_keeps_mining_replay_compatible(self) -> None:
        result = test_lab.LabTests.run_cli("scenario", "smelting", "--seed", "8", "--minutes", "754", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["village"]["smelting"]
        self.assertEqual(report["iron_in_stock"], 1)
        self.assertEqual(report["coins_paid_to_miner"], 4)
        self.assertEqual(report["coins_paid_to_charcoal_burner"], 5)
        prior = test_lab.LabTests.run_cli("scenario", "mining", "--seed", "8", "--days", "1", "--json")
        self.assertEqual(prior.returncode, 0, prior.stderr)
        self.assertEqual(json.loads(prior.stdout)["digest"],
                         "61b704e51480187fa566036633c3265a2d85355a9695d48b82e34321f7146646")
