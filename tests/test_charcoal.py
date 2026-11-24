from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.forestry import CUT_MINUTES, FIREWOOD_PRICE
from living_world.kiln import BATCH_MINUTES, KILN_STOCK
from living_world.model import (
    CHARCOAL, COIN, FARM_OWNER, FIREWOOD, CharcoalIntent, Config, FirewoodDelivery,
    FirewoodIntent, Travel, VillageConfig, VillageIntent, WorldError,
)
from living_world.persistence import Save
from living_world.routes import CHARCOAL_BURNER, FIELDS, KILN, MARKET_SQUARE, WOODCUTTER, WOODLAND, stall

BATCH = CharcoalIntent("make_charcoal", CHARCOAL_BURNER, BATCH_MINUTES)


class CharcoalTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, config: Config | None = None) -> Save:
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="charcoal")

    def test_batch_requires_input_and_physical_access_to_the_kiln(self) -> None:
        save = self.create("access")
        with self.assertRaisesRegex(WorldError, "insufficient available firewood"):
            save.submit("no-fuel", BATCH)
        with self.assertRaisesRegex(WorldError, "batch duration"):
            save.submit("too-fast", replace(BATCH, duration=1))
        with self.assertRaisesRegex(WorldError, "only the charcoal burner"):
            save.submit("farmer", replace(BATCH, actor=FARM_OWNER))
        save.submit("walk", Travel(CHARCOAL_BURNER, KILN, MARKET_SQUARE, 25))
        save.advance_to(25)
        with self.assertRaisesRegex(WorldError, "at the kiln"):
            save.submit("remote", BATCH)

    def test_canceling_a_batch_keeps_inputs_and_releases_them_for_a_retry(self) -> None:
        save = self.create("cancellation")
        save.advance_to(350)
        started = save.inspect()["snapshot"]["actions"]
        action_id = next(key for key, action in started.items()
                         if action["status"] == "started" and action["intent"].get("kind") == "make_charcoal")
        reopened = Save(save.path)
        reopened.cancel(action_id)
        before = reopened.summary()
        self.assertEqual(before["inventory"][CHARCOAL_BURNER][FIREWOOD], 2)
        self.assertEqual(before["inventory"][KILN_STOCK][CHARCOAL], 0)
        reopened.submit("retry-batch", BATCH)
        reopened.advance(minutes=BATCH_MINUTES - 1)
        self.assertEqual(reopened.summary()["inventory"][KILN_STOCK][CHARCOAL], 0)
        reopened.advance(minutes=1)
        self.assertEqual(reopened.submit("retry-batch", BATCH).status, "completed")
        after = reopened.summary()
        self.assertEqual(after["inventory"][CHARCOAL_BURNER][FIREWOOD], 0)
        self.assertEqual(after["inventory"][KILN_STOCK][CHARCOAL], 1)
        self.assertEqual(after["village"]["charcoal"]["firewood_used_at_kiln"], 2)

    def test_household_and_kiln_compete_for_the_same_last_bundle(self) -> None:
        settings = VillageConfig(rest_minutes=80)
        save = self.create("competition", Config(village=settings, starting_standing_wood=1))
        # Dispatch the buyers explicitly so both are free when the bundle arrives.
        save.mutate(lambda simulation: simulation.world.queue.clear())
        save.submit("cut-last", FirewoodIntent("cut_wood", WOODCUTTER, CUT_MINUTES))
        save.submit("burner-walk", Travel(CHARCOAL_BURNER, KILN, MARKET_SQUARE, 25))
        save.advance_to(5)
        save.submit("farmer-walk", Travel(FARM_OWNER, FIELDS[FARM_OWNER], MARKET_SQUARE, 20))
        save.advance_to(25)
        for actor in (FARM_OWNER, CHARCOAL_BURNER):
            save.submit(f"wait-{actor}", VillageIntent("rest", actor, settings.rest_minutes))
        save.advance_to(CUT_MINUTES)
        save.submit("deliver-last", FirewoodDelivery(WOODCUTTER, WOODLAND, MARKET_SQUARE, 35, firewood=1))
        save.advance_to(CUT_MINUTES + 35)
        self.assertEqual(save.summary()["inventory"][stall(WOODCUTTER)][FIREWOOD], 1)

        kiln_order = FirewoodIntent("buy_firewood", CHARCOAL_BURNER, 8, price=FIREWOOD_PRICE)
        farm_order = replace(kiln_order, actor=FARM_OWNER)
        save.submit("kiln-order", kiln_order)
        with self.assertRaisesRegex(WorldError, "insufficient available firewood"):
            save.submit("farm-order", farm_order)
        save.cancel("kiln-order")
        save.submit("farm-order", farm_order)
        with self.assertRaisesRegex(WorldError, "insufficient available firewood"):
            save.submit("retry-kiln", kiln_order)
        save.advance(minutes=8)
        report = save.summary()
        self.assertEqual(report["village"]["charcoal"]["firewood_bought_by_households"], 1)
        self.assertEqual(report["village"]["charcoal"]["firewood_bought_by_kiln"], 0)
        self.assertEqual(report["inventory"][stall(WOODCUTTER)][FIREWOOD], 0)
        self.assertEqual(report["inventory"][WOODCUTTER][COIN], 8)

    def test_mid_batch_reload_replays_and_all_goods_reconcile_to_the_journal(self) -> None:
        direct, split = self.create("direct"), self.create("split")
        split.advance_to(350)
        pending = split.summary()["village"]["charcoal"]
        self.assertEqual(pending["batch_finishes_at"], 437)
        self.assertEqual(pending["charcoal_produced"], 0)
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
        self.assertEqual(report["village"]["coin_supply"], 66)
        self.assertEqual(stock[KILN_STOCK][CHARCOAL], 4)
        self.assertTrue(any(event["kind"] == "harvest_completed" and event["payload"]["actor"] == CHARCOAL_BURNER
                            for event in journal))

    def test_an_empty_woodland_leaves_the_kiln_without_input_or_output(self) -> None:
        save = self.create("empty", Config(starting_standing_wood=0))
        save.advance(days=7)
        report = save.summary()["village"]
        self.assertEqual(report["charcoal"]["firewood_bought_by_kiln"], 0)
        self.assertEqual(report["charcoal"]["charcoal_in_stock"], 0)
        self.assertEqual(report["forestry"]["heated_rests"], 0)
        self.assertEqual(report["coin_supply"], 66)

    def test_cli_shows_the_new_supply_chain_and_keeps_the_earlier_firewood_digest(self) -> None:
        result = test_lab.LabTests.run_cli("scenario", "charcoal", "--seed", "8", "--days", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        charcoal = json.loads(result.stdout)["village"]["charcoal"]
        self.assertEqual(charcoal["firewood_bought_by_households"], 2)
        self.assertEqual(charcoal["firewood_bought_by_kiln"], 8)
        self.assertEqual(charcoal["firewood_used_at_kiln"], 8)
        self.assertEqual(charcoal["charcoal_in_stock"], 4)
        prior = test_lab.LabTests.run_cli("scenario", "firewood", "--seed", "8", "--days", "1", "--json")
        self.assertEqual(prior.returncode, 0, prior.stderr)
        self.assertEqual(json.loads(prior.stdout)["digest"],
                         "56bd5b7fbf406fb654f6f93e16a5431a289709d3c7eeb5a0ffd60985a3d9b054")
