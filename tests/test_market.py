from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.market import WEST_FARM
from living_world.model import (
    COIN, FARM_OWNER, GRAIN, SEED_GRAIN, Config, MarketIntent, VillageConfig, WorldError,
)
from living_world.persistence import Save

DAY = 1440
FIRST_BUYER = "farmhand-1"
SECOND_BUYER = "farmhand-2"


class MarketTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, seed: int = 42, **settings: int) -> Save:
        return Save.create(self.directory / f"{name}.db", seed, Config(village=VillageConfig(**settings)),
                           scenario="market")

    def test_a_pending_purchase_updates_offers_but_keeps_its_agreed_price(self) -> None:
        save = self.create("quotes")
        first = MarketIntent("buy_food", FIRST_BUYER, 8, FARM_OWNER, 1)
        first_order = save.submit("first", first)
        market = save.summary()["village"]["market"]
        self.assertIn({"seller": FARM_OWNER, "quantity": 2, "price": 2}, market["offers"])
        self.assertIn({"seller": WEST_FARM, "quantity": 3, "price": 1}, market["offers"])

        second = replace(first, actor=SECOND_BUYER)
        with self.assertRaisesRegex(WorldError, "price changed to 2"):
            save.submit("stale-quote", second)
        self.assertEqual(save.submit("first", first), first_order)
        save.submit("second", replace(second, price=2))
        reopened = Save(save.path)
        reopened.advance_to(8)
        report = reopened.summary()
        self.assertEqual(report["village"]["market"]["prices_paid"], {"1": 1, "2": 1})
        self.assertEqual(report["inventory"][FARM_OWNER][COIN], 21)
        self.assertEqual(report["inventory"][FARM_OWNER][GRAIN], 3)
        self.assertEqual(report["village"]["coin_supply"], 42)

    def test_final_offer_can_only_be_reserved_once_and_cancellation_reopens_it(self) -> None:
        save = self.create("one-meal", starting_pantry=3)
        first = MarketIntent("buy_food", FIRST_BUYER, 8, FARM_OWNER, 2)
        second = replace(first, actor=SECOND_BUYER)
        save.submit("first", first)
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "no grain offered"):
            save.submit("second", second)
        self.assertEqual(save.inspect(journal=True), before)
        save.cancel("first")
        save.submit("second", second)
        save.advance_to(8)
        self.assertEqual(save.summary()["village"]["purchases"], 1)
        self.assertEqual(save.summary()["inventory"][FARM_OWNER][GRAIN], 2)

    def test_seed_shock_keeps_reserved_seed_and_reconstructs_the_inventory(self) -> None:
        save = self.create("seed", starting_seed=5)
        shift = MarketIntent("harvest", FIRST_BUYER, 95, FARM_OWNER)
        save.submit("shift", shift)
        save.market_shock("seed-shortage")
        report = save.inspect(journal=True)
        self.assertEqual(report["snapshot"]["inventory"][FARM_OWNER][SEED_GRAIN], 1)
        shock = report["journal"][-1]
        self.assertEqual(shock["kind"], "seed_shortage")
        self.assertEqual(shock["payload"]["movements"][0]["quantity"], 4)

        recovered = Save(save.path)
        recovered.advance(days=7)
        journal = recovered.inspect(journal=True)["journal"]
        self.assertEqual(recovered.submit("shift", shift).status, "completed")
        stock = journal[0]["payload"]["inventory"]
        for event in journal[1:]:
            for movement in event["payload"].get("movements", ()):
                source = movement["source"]
                destination = movement["destination"]
                good = movement["good"]
                quantity = movement["quantity"]
                if source is not None:
                    stock[source][good] -= quantity
                    self.assertGreaterEqual(stock[source][good], 0)
                if destination is not None:
                    stock[destination][good] = stock[destination].get(good, 0) + quantity
        self.assertEqual(stock, recovered.summary()["inventory"])

    def test_seed_shortage_switches_buyers_and_labor_to_the_working_farm(self) -> None:
        baseline = self.create("baseline")
        shortage = self.create("shortage")
        shortage.advance_to(DAY)
        shortage.market_shock("seed-shortage")
        for save in (baseline, shortage):
            save.advance_to(7 * DAY)
        normal, reduced = (save.summary()["village"] for save in (baseline, shortage))
        normal_market, reduced_market = normal["market"], reduced["market"]
        self.assertLess(reduced["grain_produced"], normal["grain_produced"])
        self.assertLess(reduced_market["harvests_by_farm"][FARM_OWNER],
                        normal_market["harvests_by_farm"][FARM_OWNER])
        self.assertGreater(reduced_market["harvests_by_farm"][WEST_FARM],
                           normal_market["harvests_by_farm"][WEST_FARM])
        self.assertGreater(reduced_market["purchases_by_seller"][WEST_FARM],
                           normal_market["purchases_by_seller"][WEST_FARM])
        self.assertEqual(reduced["coin_supply"], normal["coin_supply"])

        def suppliers(save: Save, *, since: int = 0, until: int = 7 * DAY + 1) -> set[str]:
            return {
                event["payload"]["farm"] for event in save.inspect(journal=True)["journal"]
                if event["kind"] == "buy_food_completed" and since <= event["minute"] < until
                and event["payload"]["actor"] == FIRST_BUYER
            }

        self.assertIn(FARM_OWNER, suppliers(shortage, until=DAY))
        self.assertIn(FARM_OWNER, suppliers(baseline, since=3 * DAY))
        self.assertEqual(suppliers(shortage, since=3 * DAY), {WEST_FARM})

    def test_worker_loss_cancels_pending_work_and_survives_reopen(self) -> None:
        save = self.create("worker")
        shift = MarketIntent("harvest", FIRST_BUYER, 95, FARM_OWNER)
        save.submit("shift", shift)
        alternative = replace(shift, actor=SECOND_BUYER)
        with self.assertRaisesRegex(WorldError, "hired field shift is occupied"):
            save.submit("same-shift", alternative)
        save.market_shock("worker-loss")
        reopened = Save(save.path)
        after = reopened.inspect(journal=True)
        self.assertEqual(reopened.summary()["village"]["market"]["available_farmhands"], 1)
        self.assertEqual(after["snapshot"]["actions"]["shift"]["status"], "canceled")
        self.assertEqual(after["journal"][-1]["cause_id"], after["journal"][-2]["id"])
        self.assertEqual(after["snapshot"]["inventory"][FARM_OWNER][SEED_GRAIN], 400)
        with self.assertRaisesRegex(WorldError, "unavailable for field work"):
            reopened.submit("retry-work", shift)
        reopened.submit("replacement", alternative)
        reopened.advance_to(95)
        self.assertEqual(reopened.submit("replacement", alternative).status, "completed")

    def test_market_replays_through_save_reload_with_the_same_shock(self) -> None:
        baseline = self.create("normal")
        baseline.advance(days=7)
        direct = self.create("direct")
        split = self.create("split")
        for save in (direct, split):
            save.advance_to(DAY)
            save.market_shock("worker-loss")
        direct.advance_to(7 * DAY)
        split.advance_to(3 * DAY + 14)
        Save(split.path).advance_to(7 * DAY)
        self.assertEqual(direct.inspect(journal=True), split.inspect(journal=True))
        reduced, normal = (save.summary()["village"] for save in (split, baseline))
        self.assertLess(reduced["harvests"], normal["harvests"])
        self.assertLess(reduced["grain_produced"], normal["grain_produced"])
        self.assertEqual(reduced["coin_supply"], normal["coin_supply"])

    def test_market_cli_offers_two_shocks_and_the_earlier_village_digest(self) -> None:
        for shock in ("seed-shortage", "worker-loss"):
            with self.subTest(shock=shock):
                result = test_lab.LabTests.run_cli("scenario", "market", "--seed", "42",
                                                   "--days", "7", "--shock", shock, "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["actors"], 4)
                self.assertEqual(report["village"]["market"]["shocks"][0]["minute"], DAY)
        prior = test_lab.LabTests.run_cli("scenario", "village", "--seed", "42", "--json")
        self.assertEqual(prior.returncode, 0, prior.stderr)
        self.assertEqual(json.loads(prior.stdout)["digest"],
                         "ebe11637f9878d038fc751289a8006db697e7a7642f08a88b940ab4135f9d7c8")
