from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.forestry import CUT_MINUTES, FIREWOOD_PRICE, WOODLAND_STOCK
from living_world.model import (
    COIN, FARM_OWNER, FIREWOOD, STANDING_WOOD, Config, FirewoodDelivery, FirewoodIntent,
    VillageConfig, WorldError,
)
from living_world.persistence import Save
from living_world.routes import FARMS, MARKET_SQUARE, WOODCUTTER, WOODLAND, WOODPILE, stall

SINGLE_CUT = FirewoodIntent("cut_wood", WOODCUTTER, CUT_MINUTES)
SINGLE_LOAD = FirewoodDelivery(WOODCUTTER, WOODLAND, MARKET_SQUARE, 35, firewood=1)


class FirewoodTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, *, standing: int = 240, hand_coins: int = 3) -> Save:
        config = Config(starting_standing_wood=standing, village=VillageConfig(starting_hand_coin=hand_coins))
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="firewood")

    def test_extraction_consumes_the_last_standing_wood_and_cannot_create_more(self) -> None:
        with self.assertRaisesRegex(WorldError, "starting_standing_wood"):
            Config(starting_standing_wood=-1)
        save = self.create("finite", standing=1)
        with self.assertRaisesRegex(WorldError, "insufficient available standing_wood"):
            save.submit("too-much", replace(SINGLE_CUT, quantity=2))
        save.submit("last-tree", SINGLE_CUT)
        save.advance_to(CUT_MINUTES)
        report = save.summary()
        self.assertEqual(report["inventory"][WOODLAND_STOCK][STANDING_WOOD], 0)
        self.assertEqual(report["inventory"][WOODPILE][FIREWOOD], 1)
        with self.assertRaisesRegex(WorldError, "insufficient available standing_wood"):
            save.submit("empty-cut", SINGLE_CUT)
        save.advance(days=7)
        after = save.summary()["village"]["forestry"]
        self.assertEqual(after["firewood_cut"], 1)
        self.assertEqual(after["firewood_delivered"], 1)
        self.assertEqual(after["firewood_burned"], 1)

    def test_canceling_firewood_cargo_releases_it_without_stocking_the_stall(self) -> None:
        save = self.create("cancellation", standing=1)
        save.submit("cut", SINGLE_CUT)
        save.advance_to(CUT_MINUTES)
        save.submit("delivery", SINGLE_LOAD)
        save.advance(minutes=20)
        reopened = Save(save.path)
        pending = reopened.summary()
        self.assertEqual(pending["village"]["travel"]["in_transit"][WOODCUTTER]["firewood"], 1)
        self.assertIsNone(pending["village"]["forestry"]["market_offer"])
        reopened.cancel("delivery")
        stock = reopened.summary()["inventory"]
        self.assertEqual(stock[WOODPILE][FIREWOOD], 1)
        self.assertEqual(stock[stall(WOODCUTTER)][FIREWOOD], 0)
        reopened.submit("replacement", SINGLE_LOAD)
        reopened.advance(minutes=35)
        report = reopened.summary()
        self.assertEqual(report["inventory"][WOODPILE][FIREWOOD], 0)
        self.assertEqual(report["village"]["forestry"]["firewood_delivered"], 1)

    def test_firewood_trade_needs_a_local_funded_buyer_and_reserves_the_last_bundle(self) -> None:
        save = self.create("sale", standing=1, hand_coins=5)
        with self.assertRaisesRegex(WorldError, "customer at the market square"):
            save.submit("remote", FirewoodIntent("buy_firewood", FARM_OWNER, 8, price=FIREWOOD_PRICE))
        save.submit("cut", SINGLE_CUT)
        save.advance_to(CUT_MINUTES)
        save.submit("delivery", SINGLE_LOAD)
        save.advance_to(CUT_MINUTES + 35)

        first = FirewoodIntent("buy_firewood", "farmhand-1", 8, price=FIREWOOD_PRICE)
        with self.assertRaisesRegex(WorldError, "costs 2 coins"):
            save.submit("wrong-price", replace(first, price=1))
        save.submit("buy", first)
        with self.assertRaisesRegex(WorldError, "insufficient available firewood"):
            save.submit("competing-buyer", replace(first, actor="farmhand-2"))
        save.advance(minutes=8)
        report = save.summary()
        self.assertEqual(report["inventory"]["farmhand-1"][FIREWOOD], 1)
        self.assertEqual(report["inventory"]["farmhand-1"][COIN], 3)
        self.assertEqual(report["inventory"][WOODCUTTER][COIN], 8)
        self.assertEqual(report["village"]["forestry"]["firewood_sold"], 1)
        with self.assertRaisesRegex(WorldError, "at their own hearth"):
            save.submit("market-fire", FirewoodIntent("burn_firewood", "farmhand-1", 10))

    def test_warmth_is_paid_for_and_improves_farmhouse_rest(self) -> None:
        warmed = self.create("warm")
        depleted = self.create("depleted", standing=0)
        for save in (warmed, depleted):
            save.advance(days=1)
        warm_metrics, cold_metrics = (save.summary()["village"]["forestry"] for save in (warmed, depleted))
        self.assertEqual(warm_metrics["firewood_sold"], 2)
        self.assertEqual(warm_metrics["firewood_burned"], 2)
        self.assertEqual(warm_metrics["coin_paid_for_firewood"], 4)
        self.assertTrue(all(hearth["warm"] for hearth in warm_metrics["hearths"].values()))
        self.assertGreater(warm_metrics["heated_rests"], 0)
        self.assertEqual(cold_metrics["heated_rests"], 0)
        self.assertEqual(cold_metrics["firewood_cut"], 0)

        def farmhouse_rests(save: Save) -> list[dict]:
            return [event["payload"]["needs"] for event in save.inspect(journal=True)["journal"]
                    if event["kind"] == "rest_completed" and event["payload"]["actor"] in FARMS]

        self.assertTrue(any(rest["heated"] and rest["fatigue"] == 0
                            for rest in farmhouse_rests(warmed)))
        self.assertTrue(any(not rest["heated"] and rest["fatigue"] > 0
                            for rest in farmhouse_rests(depleted)))

    def test_mid_delivery_save_preserves_the_whole_ledger(self) -> None:
        continuous = self.create("continuous")
        staged = self.create("staged")
        staged.advance_to(100)
        in_transit = staged.summary()["village"]["travel"]["in_transit"]
        self.assertEqual(in_transit[WOODCUTTER]["arrives_at"], 124)
        for save in (continuous, Save(staged.path)):
            save.advance_to(7 * 1440)
        self.assertEqual(continuous.inspect(journal=True), staged.inspect(journal=True))

        journal = staged.inspect(journal=True)["journal"]
        inventory = journal[0]["payload"]["inventory"]
        for event in journal[1:]:
            for move in event["payload"].get("movements", ()):
                if move["source"] is not None:
                    balance = inventory[move["source"]]
                    balance[move["good"]] -= move["quantity"]
                    self.assertGreaterEqual(balance[move["good"]], 0)
                if move["destination"] is not None:
                    balance = inventory[move["destination"]]
                    balance[move["good"]] = balance.get(move["good"], 0) + move["quantity"]
        report = staged.summary()
        self.assertEqual(inventory, report["inventory"])
        self.assertEqual(report["village"]["coin_supply"], 48)

    def test_installed_scenario_brings_firewood_to_market_and_keeps_prior_routes_digest(self) -> None:
        result = test_lab.LabTests.run_cli("scenario", "firewood", "--seed", "8", "--minutes", "125", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        metrics = json.loads(result.stdout)["village"]
        self.assertEqual(metrics["forestry"]["market_offer"], {"seller": WOODCUTTER, "quantity": 3, "price": 2})
        self.assertEqual(metrics["travel"]["grain_delivered"], 6)
        earlier = test_lab.LabTests.run_cli("scenario", "routes", "--seed", "8", "--minutes", "70", "--json")
        self.assertEqual(earlier.returncode, 0, earlier.stderr)
        self.assertEqual(json.loads(earlier.stdout)["digest"],
                         "7d9c5f04b59a3b14af070977617ffe5732675b1d14ee74da3043eea0260f824d")
