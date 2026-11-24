from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.model import (
    COIN, FARM_OWNER, GRAIN, SEED_GRAIN, Config, MarketIntent, Transfer, Travel, VillageConfig,
    WorldError,
)
from living_world.persistence import Save
from living_world.routes import FIELDS, MARKET_SQUARE, WEST_FARM, pantry, stall

EAST_FIELD = FIELDS[FARM_OWNER]
WEST_FIELD = FIELDS[WEST_FARM]
EAST_CART = Travel(FARM_OWNER, EAST_FIELD, MARKET_SQUARE, 20, 3)
WEST_CART = Travel(WEST_FARM, WEST_FIELD, MARKET_SQUARE, 45, 3)
BUYER = "farmhand-1"


class RoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str) -> Save:
        config = Config(village=VillageConfig(starting_hand_coin=5))
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="routes")

    def test_sellers_can_only_fill_orders_after_grain_arrives(self) -> None:
        save = self.create("delivery-order")
        save.submit("east", EAST_CART)
        save.submit("west", WEST_CART)
        save.advance_to(19)
        before = save.summary()
        self.assertEqual(before["village"]["market"]["offers"], [])
        self.assertEqual(before["village"]["travel"]["in_transit"][FARM_OWNER]["arrives_at"], 20)
        self.assertEqual(before["inventory"][pantry(FARM_OWNER)][GRAIN], 5)
        self.assertEqual(before["inventory"][stall(FARM_OWNER)][GRAIN], 0)

        save.advance_to(20)
        report = save.summary()
        self.assertEqual(report["village"]["market"]["offers"],
                         [{"seller": FARM_OWNER, "quantity": 3, "price": 1}])
        self.assertEqual(report["village"]["travel"]["last_reached_locations"][FARM_OWNER], MARKET_SQUARE)
        sale = MarketIntent("buy_food", BUYER, 8, WEST_FARM, 1)
        with self.assertRaisesRegex(WorldError, "no grain offered"):
            save.submit("too-early", sale)
        save.submit("east-sale", replace(sale, farm=FARM_OWNER))
        save.advance_to(45)
        self.assertEqual(save.summary()["inventory"][BUYER][GRAIN], 1)
        self.assertEqual(save.summary()["inventory"][stall(WEST_FARM)][GRAIN], 3)
        save.submit("west-sale", sale)
        save.advance_to(53)
        inventory = save.summary()["inventory"]
        self.assertEqual(inventory[BUYER], {COIN: 3, GRAIN: 2})
        self.assertEqual(inventory[stall(WEST_FARM)][GRAIN], 2)

    def test_work_and_shopping_require_arrival_and_only_direct_roads_can_be_taken(self) -> None:
        save = self.create("access")
        walk = Travel(BUYER, MARKET_SQUARE, EAST_FIELD, 20)
        work = MarketIntent("harvest", BUYER, 95, FARM_OWNER)
        with self.assertRaisesRegex(WorldError, "requires being at east-farm"):
            save.submit("remote-work", work)
        with self.assertRaisesRegex(WorldError, "takes 20"):
            save.submit("too-fast", replace(walk, duration=1))
        with self.assertRaisesRegex(WorldError, "no direct road"):
            save.submit("skip-square", replace(EAST_CART, destination=WEST_FIELD, grain=0))

        save.submit("walk", walk)
        with self.assertRaisesRegex(WorldError, "is traveling"):
            save.submit("send-to-transit", Transfer("farmhand-2", BUYER, 1, 5))
        save.advance_to(19)
        with self.assertRaisesRegex(WorldError, "requires being at east-farm"):
            save.submit("work-before-arrival", work)
        save.advance_to(20)
        with self.assertRaisesRegex(WorldError, "requires being at market-square"):
            save.submit("remote-shopping", MarketIntent("buy_food", BUYER, 8, WEST_FARM, 1))
        save.submit("field-shift", work)
        save.advance_to(115)
        self.assertEqual(save.submit("field-shift", work).status, "completed")
        self.assertEqual(save.summary()["inventory"][BUYER][COIN], 7)

    def test_canceling_a_delivery_releases_grain_without_moving_it(self) -> None:
        save = self.create("canceled-delivery")
        whole_pantry = replace(EAST_CART, grain=5)
        save.submit("first-trip", whole_pantry)
        save.advance_to(10)
        reopened = Save(save.path)
        reopened.cancel("first-trip")
        after = reopened.summary()
        self.assertNotIn(FARM_OWNER, after["village"]["travel"]["in_transit"])
        self.assertEqual(after["village"]["travel"]["last_reached_locations"][FARM_OWNER], EAST_FIELD)
        self.assertEqual(after["inventory"][pantry(FARM_OWNER)][GRAIN], 5)
        self.assertEqual(after["inventory"][stall(FARM_OWNER)][GRAIN], 0)
        reopened.submit("replacement", whole_pantry)
        reopened.advance_to(29)
        self.assertEqual(reopened.summary()["inventory"][stall(FARM_OWNER)][GRAIN], 0)
        reopened.advance_to(30)
        self.assertEqual(reopened.summary()["inventory"][stall(FARM_OWNER)][GRAIN], 5)

    def test_mid_trip_save_reload_matches_the_complete_run_and_balances_stock(self) -> None:
        uninterrupted = self.create("full")
        split = self.create("split")
        split.advance_to(50)
        self.assertIn(WEST_FARM, split.summary()["village"]["travel"]["in_transit"])
        for save in (uninterrupted, Save(split.path)):
            save.advance_to(7 * 1440)
        self.assertEqual(split.inspect(journal=True), uninterrupted.inspect(journal=True))

        journal = split.inspect(journal=True)["journal"]
        stock = journal[0]["payload"]["inventory"]
        for event in journal[1:]:
            for move in event["payload"].get("movements", ()):
                if move["source"] is not None:
                    stock[move["source"]][move["good"]] -= move["quantity"]
                    self.assertGreaterEqual(stock[move["source"]][move["good"]], 0)
                if move["destination"] is not None:
                    account = stock[move["destination"]]
                    account[move["good"]] = account.get(move["good"], 0) + move["quantity"]
        report = split.summary()
        self.assertEqual(stock, report["inventory"])
        self.assertEqual(report["village"]["coin_supply"], 46)
        self.assertEqual(report["village"]["seed_in_stock"], 800 - report["village"]["harvests"])
        self.assertGreater(report["village"]["travel"]["grain_delivered"], 0)

    def test_routes_cli_moves_trade_to_west_after_east_loses_seed(self) -> None:
        common = ("scenario", "routes", "--seed", "8", "--days", "7", "--json")
        baseline = test_lab.LabTests.run_cli(*common)
        shortage = test_lab.LabTests.run_cli(*common, "--shock", "seed-shortage")
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertEqual(shortage.returncode, 0, shortage.stderr)
        normal, reduced = (json.loads(result.stdout) for result in (baseline, shortage))
        self.assertEqual(reduced["inventory"][pantry(FARM_OWNER)][SEED_GRAIN], 0)
        self.assertGreater(reduced["village"]["market"]["purchases_by_seller"][WEST_FARM],
                           normal["village"]["market"]["purchases_by_seller"][WEST_FARM])
        self.assertGreater(reduced["village"]["travel"]["trips_by_road"][WEST_FIELD],
                           normal["village"]["travel"]["trips_by_road"][WEST_FIELD])
        self.assertEqual(reduced["village"]["grain_eaten"], normal["village"]["grain_eaten"])

    def test_original_market_scenario_keeps_its_digest(self) -> None:
        result = test_lab.LabTests.run_cli("scenario", "market", "--seed", "8", "--days", "7", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["digest"],
                         "976ad97831668d5c4d3d611a001ca8ce6a1afc13b287c5b45f3da28e558788ad")
