from __future__ import annotations

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier

from living_world.model import (
    COIN, FARM_OWNER, GRAIN, SEED_GRAIN, Config, VillageConfig, VillageIntent, WorldError,
)
from living_world.persistence import Save
from living_world.simulation import Simulation


class VillageTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, seed: int = 42, **settings: int) -> Save:
        return Save.create(self.directory / f"{name}.db", seed, Config(village=VillageConfig(**settings)),
                           scenario="village")

    def test_zero_player_food_loop_balances_stocks_and_cash_across_seeds(self) -> None:
        for seed in (1, 7, 42, 83, 541):
            with self.subTest(seed=seed):
                save = self.create(f"baseline-{seed}", seed)
                save.advance(days=7)
                state = save.inspect(journal=True)
                metrics = save.summary()["village"]
                self.assertEqual(len(state["snapshot"]["actors"]), 3)
                self.assertGreater(metrics["grain_produced"], 0)
                self.assertGreater(metrics["grain_eaten"], 0)
                self.assertGreater(metrics["coin_paid_in_wages"], 0)
                self.assertGreater(metrics["purchases"], 0)
                self.assertGreater(metrics["rests"], 0)
                self.assertEqual(metrics["coin_supply"], 24)
                self.assertEqual(metrics["failed_actions"], 0)
                self.assertEqual(metrics["grain_in_stock"],
                                 5 + metrics["grain_produced"] - metrics["grain_eaten"])
                self.assertEqual(metrics["seed_in_stock"], 400 - metrics["harvests"])

                journal = state["journal"]
                accounts = journal[0]["payload"]["inventory"]
                for event in journal[1:]:
                    cause_id = event["cause_id"]
                    self.assertIsNotNone(cause_id)
                    self.assertLess(cause_id, event["id"])
                    for move in event["payload"].get("movements", ()):
                        source, dest = move["source"], move["destination"]
                        good, quantity = move["good"], move["quantity"]
                        if source is not None:
                            accounts[source][good] -= quantity
                            self.assertGreaterEqual(accounts[source][good], 0)
                        if dest is not None:
                            accounts[dest][good] = accounts[dest].get(good, 0) + quantity
                self.assertEqual(accounts, state["snapshot"]["inventory"])

    def test_autonomous_continuation_preserves_pending_work_rng_and_journal(self) -> None:
        uninterrupted = self.create("uninterrupted")
        split = self.create("split")
        split.advance_to(600)
        split_snapshot = split.inspect()["snapshot"]
        self.assertTrue(any(action["status"] == "started"
                            for action in split_snapshot["actions"].values()))
        Save(split.path).advance_to(10_080)
        uninterrupted.advance_to(10_080)
        self.assertEqual(split.inspect(journal=True), uninterrupted.inspect(journal=True))

    def test_npc_decisions_see_work_completed_in_the_same_minute(self) -> None:
        seed = 42
        preview = Simulation.create(seed, Config(), "village")
        minute = next(event.minute for event in preview.world.queue if event.subject == "farmhand-1")
        save = self.create("priority", seed, starting_pantry=0, starting_seed=1,
                           harvest_minutes=minute, meal_relief=1)
        save.submit("harvest", VillageIntent("harvest", FARM_OWNER, minute))
        save.advance_to(minute)
        journal = save.inspect(journal=True)["journal"]
        harvest = next(event for event in journal if event["kind"] == "harvest_completed")
        purchase = next(event for event in journal if event["kind"] == "action_started"
                        and event["payload"]["intent"]["actor"] == "farmhand-1"
                        and event["payload"]["type"] == "buy_food")
        self.assertEqual(harvest["minute"], purchase["minute"])
        self.assertLess(harvest["id"], purchase["id"])

    def test_last_meal_can_only_be_reserved_by_one_buyer(self) -> None:
        save = self.create("one-meal", starting_pantry=1, starting_seed=0)
        first = VillageIntent("buy_food", "farmhand-1", 8)
        second = replace(first, actor="farmhand-2")
        save.submit("first", first)
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "insufficient available grain"):
            save.submit("second", second)
        self.assertEqual(save.inspect(journal=True), before)

        save.cancel("first")
        save.submit("second", second)
        save.advance_to(8)
        self.assertEqual(save.submit("second", second).status, "completed")
        stock = save.summary()["inventory"]
        self.assertEqual((stock[FARM_OWNER][GRAIN], stock[FARM_OWNER][COIN]), (0, 19))
        self.assertEqual((stock["farmhand-2"][GRAIN], stock["farmhand-2"][COIN]), (1, 2))
        self.assertEqual(save.summary()["village"]["purchases"], 1)

    def test_simultaneous_save_connections_serialize_purchase_reservations(self) -> None:
        save = self.create("competing-buyers", starting_pantry=1, starting_seed=0)
        ready = Barrier(2)

        def buy(actor: str) -> str:
            ready.wait(timeout=5)
            try:
                return Save(save.path).submit(actor, VillageIntent("buy_food", actor, 8)).status
            except WorldError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, ("farmhand-1", "farmhand-2")))
        self.assertCountEqual(results, ["started", "insufficient available grain for farm-owner"])
        save.advance_to(8)
        self.assertEqual(save.summary()["village"]["purchases"], 1)

    def test_purchase_without_coins_rejected_and_write_failure_preserves_both_goods(self) -> None:
        save = self.create("budget", starting_seed=0, starting_hand_coin=0)
        purchase = VillageIntent("buy_food", "farmhand-1", 8)
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "insufficient available coin"):
            save.submit("sale", purchase)
        self.assertEqual(save.inspect(journal=True), before)

        save = self.create("failing-write", starting_seed=0)
        save.submit("sale", purchase)
        before = save.inspect(journal=True)
        with closing(sqlite3.connect(save.path)) as db, db:
            db.execute("""CREATE TRIGGER fail_snapshot BEFORE UPDATE ON world
                        BEGIN SELECT RAISE(ABORT, 'injected purchase failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected purchase failure"):
            save.advance_to(8)
        self.assertEqual(save.inspect(journal=True), before)

    def test_seed_shortage_changes_stock_and_npc_decisions(self) -> None:
        baseline = self.create("baseline")
        shortage = self.create("shortage", starting_seed=0)
        for save in (baseline, shortage):
            save.advance(days=7)
        healthy, depleted = (save.summary()["village"] for save in (baseline, shortage))
        self.assertEqual(depleted["coin_supply"], healthy["coin_supply"])
        self.assertEqual(depleted["grain_in_stock"], 0)
        self.assertEqual(depleted["grain_produced"], 0)
        self.assertLess(depleted["purchases"], healthy["purchases"])
        self.assertGreater(depleted["needs"]["farmhand-1"]["hunger"],
                           healthy["needs"]["farmhand-1"]["hunger"])
        waits = (event["payload"]["rejected"]
                 for event in shortage.inspect(journal=True)["journal"]
                 if event["kind"] == "decision_waited")
        self.assertTrue(any(SEED_GRAIN in wait.get("harvest", "") for wait in waits))
