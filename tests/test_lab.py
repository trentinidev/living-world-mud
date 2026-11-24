from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from random import Random

from living_world.model import Config, Transfer, WorldError
from living_world.persistence import Save
from living_world.simulation import Simulation

DELIVERY = Transfer("storekeeper", "neighbor", 2, 10)


class LabTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "world.db"

    def test_same_seed_and_inputs_produce_identical_state_and_events(self) -> None:
        first = Save.create(self.path, 42)
        second = Save.create(self.path.with_name("replay.db"), 42)
        for save in (first, second):
            save.submit("delivery", DELIVERY)
            save.advance_to(10)
        self.assertEqual(first.inspect(journal=True), second.inspect(journal=True))
        different = Save.create(self.path.with_name("different.db"), 43)
        self.assertNotEqual(first.inspect()["snapshot"]["rng_state"],
                            different.inspect()["snapshot"]["rng_state"])

    def test_simultaneous_events_obey_priority_and_then_insertion_order(self) -> None:
        simulation = Simulation.create(42, Config())
        simulation.schedule(5, 2, "third")
        simulation.schedule(5, 1, "first")
        simulation.schedule(5, 1, "second")
        self.assertEqual([event.subject for event in sorted(simulation.world.queue)],
                         ["first", "second", "third"])

        save = Save.create(self.path, 42, Config(neighbor_starting_grain=3))
        save.submit("z-first", DELIVERY)
        save.submit("a-second", Transfer("neighbor", "storekeeper", 1, 10))
        Save(self.path).advance_to(10)
        transfers = [event["payload"]["action"] for event in save.inspect(journal=True)["journal"]
                     if event["kind"] == "goods_transferred"]
        self.assertEqual(transfers, ["z-first", "a-second"])

    def test_reopening_mid_action_preserves_queue_and_rng(self) -> None:
        uninterrupted = Save.create(self.path, 42)
        pending = Save.create(self.path.with_name("pending.db"), 42)
        for save in (uninterrupted, pending):
            save.submit("delivery", DELIVERY)

        pending.advance_to(5)
        self.assertEqual(Save(self.path.with_name("pending.db")).summary()["pending_events"], 1)
        with pending.connect(readonly=True) as db:
            restored = pending.load_world(db)
        created = Simulation.create(42, Config()).world
        first, second = Random(), Random()
        first.setstate(restored.rng_state)
        second.setstate(created.rng_state)
        self.assertEqual(first.getrandbits(128), second.getrandbits(128))

        Save(pending.path).advance_to(15)
        uninterrupted.advance_to(15)
        self.assertEqual(uninterrupted.inspect(journal=True), pending.inspect(journal=True))

    def test_sqlite_failure_rolls_back_pending_action_journal_and_clock(self) -> None:
        save = Save.create(self.path, 42)
        save.submit("delivery", DELIVERY)
        before = save.inspect(journal=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TRIGGER fail_snapshot BEFORE UPDATE ON world
                        BEGIN SELECT RAISE(ABORT, 'injected snapshot failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected snapshot failure"):
            save.advance_to(15)
        self.assertEqual(save.inspect(journal=True), before)

        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TRIGGER fail_snapshot")
        save.advance_to(15)
        save.advance_to(15)
        after = save.inspect(journal=True)
        self.assertEqual(after["snapshot"]["inventory"]["neighbor"]["grain"], 2)
        self.assertEqual(sum(event["kind"] == "goods_transferred" for event in after["journal"]), 1)

    def test_retries_and_conflicting_key(self) -> None:
        save = Save.create(self.path, 42)
        started = save.submit("delivery", DELIVERY)
        self.assertEqual(Save(self.path).submit("delivery", DELIVERY), started)
        with self.assertRaisesRegex(WorldError, "different intent"):
            save.submit("delivery", replace(DELIVERY, quantity=3))
        save.advance_to(10)
        before = save.inspect(journal=True)
        self.assertEqual(save.submit("delivery", DELIVERY).status, "completed")
        save.advance_to(10)
        self.assertEqual(save.inspect(journal=True), before)

    def test_cancel_and_revalidation_release_reservations(self) -> None:
        save = Save.create(self.path, 42)
        save.submit("cancel-me", DELIVERY)
        canceled = save.cancel("cancel-me")
        self.assertEqual(Save(self.path).cancel("cancel-me"), canceled)
        self.assertEqual(save.submit("next", DELIVERY).status, "started")
        save.advance_to(10)
        self.assertEqual(save.summary()["inventory"]["neighbor"]["grain"], 2)

        simulation = Simulation.create(42, Config())
        initial = simulation.available("storekeeper", "grain")
        simulation.submit("fail-me", DELIVERY)
        self.assertEqual(simulation.available("storekeeper", "grain"), initial - 2)
        simulation.world.actors["neighbor"] = replace(
            simulation.world.actors["neighbor"], location="elsewhere",
        )
        simulation.advance_to(10)
        self.assertEqual(simulation.available("storekeeper", "grain"), initial)
        self.assertEqual(simulation.world.actions["fail-me"].status, "failed")
        self.assertEqual(simulation.events[-1].kind, "action_failed")

    def test_invalid_configuration_commands_and_time_leave_state_unchanged(self) -> None:
        for overlay in (
            {"max_action_minutes": False}, {"minutes_per_day": 0},
            {"starting_grain_min": 20, "starting_grain_max": 4}, {"extra": 4},
        ):
            with self.subTest(overlay=overlay), self.assertRaises(WorldError):
                Config.from_mapping(overlay)
        save = Save.create(self.path, 42, Config(max_events_per_advance=1, neighbor_starting_grain=3))
        save.advance_to(1)
        before = save.inspect(journal=True)
        for changes, message in (
            ({"duration": 0}, "duration"), ({"quantity": True}, "quantity"),
            ({"target": "unknown"}, "unknown target"), ({"target": "storekeeper"}, "different"),
            ({"good": "iron"}, "unknown good"), ({"quantity": 100}, "insufficient"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(WorldError, message):
                save.submit("invalid", replace(DELIVERY, **changes))
        with self.assertRaisesRegex(WorldError, "target minute"):
            save.advance_to(0)
        self.assertEqual(save.inspect(journal=True), before)

        save.submit("first", DELIVERY)
        save.submit("second", Transfer("neighbor", "storekeeper", 1, 10))
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "event limit"):
            save.advance_to(11)
        self.assertEqual(save.inspect(journal=True), before)

    def test_conservation_with_transfers_and_retries_across_seeds(self) -> None:
        for seed in range(-5, 5):
            with self.subTest(seed=seed):
                save = Save.create(self.path.with_name(f"seed-{seed}.db"), seed)
                initial = save.summary()["inventory"]["storekeeper"]["grain"]
                for index in range(8):
                    actor, target = ("storekeeper", "neighbor") if index % 2 == 0 else (
                        "neighbor", "storekeeper",
                    )
                    intent = Transfer(actor, target, 2, 1)
                    save.submit(f"move-{index}", intent)
                    save.advance(minutes=1)
                    save.submit(f"move-{index}", intent)
                    inventory = save.summary()["inventory"]
                    self.assertTrue(all(stock["grain"] >= 0 for stock in inventory.values()))
                    self.assertEqual(sum(stock["grain"] for stock in inventory.values()), initial)

    def test_headless_cli_and_existing_save_protection(self) -> None:
        creation = self.run_cli("create", "--seed", "42", "--save", str(self.path))
        self.assertEqual(creation.returncode, 0, creation.stderr)
        duplicate = self.run_cli("create", "--seed", "43", "--save", str(self.path))
        self.assertNotEqual(duplicate.returncode, 0)
        advanced = self.run_cli("simulate", "--save", str(self.path), "--days", "1", "--headless")
        self.assertEqual(advanced.returncode, 0, advanced.stderr)
        self.assertEqual(json.loads(advanced.stdout)["minute"], 1440)
        self.assertEqual(json.loads(advanced.stdout)["seed"], 42)
        smoke = self.run_cli("scenario", "lab", "--seed", "42", "--json")
        self.assertEqual(smoke.returncode, 0, smoke.stderr)
        self.assertEqual(json.loads(smoke.stdout)["journal"][-1]["kind"], "goods_transferred")

    @staticmethod
    def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "living_world", *args],
                              capture_output=True, text=True, check=False)
