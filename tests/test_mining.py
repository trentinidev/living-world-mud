from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.mining import DEPOSIT, SHIFT_MINUTES, STALL_TARGET
from living_world.model import (
    FARM_OWNER, IRON_ORE, ORE_IN_VEIN, Config, MiningIntent, OreDelivery, WorldError,
)
from living_world.persistence import Save
from living_world.routes import MARKET_SQUARE, MINE, MINE_STOCK, MINER, stall

SHIFT = MiningIntent("mine_ore", MINER, SHIFT_MINUTES, 3)
LOAD = OreDelivery(MINER, MINE, MARKET_SQUARE, 40, ore=3)


class MiningTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, config: Config | None = None) -> Save:
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="mining")

    def test_the_last_partial_shift_drains_the_deposit_and_caps_extraction(self) -> None:
        with self.assertRaisesRegex(WorldError, "starting_ore_deposit"):
            Config(starting_ore_deposit=-1)
        save = self.create("finite", Config(starting_ore_deposit=2))
        with self.assertRaisesRegex(WorldError, "insufficient available ore_in_vein"):
            save.submit("overdraw", SHIFT)
        last_shift = replace(SHIFT, quantity=2)
        save.submit("last-shift", last_shift)
        save.advance_to(SHIFT_MINUTES - 1)
        before = save.summary()["village"]["mining"]
        self.assertEqual(before["deposit_remaining"], 2)
        self.assertEqual(before["ore_extracted"], 0)
        save.advance_to(SHIFT_MINUTES)
        self.assertEqual(save.submit("last-shift", last_shift).status, "completed")
        after = save.summary()["village"]["mining"]
        self.assertEqual(after["deposit_remaining"], 0)
        self.assertEqual(after["ore_at_mine"], 2)
        self.assertEqual(after["ore_at_market"], 0)
        with self.assertRaisesRegex(WorldError, "insufficient available ore_in_vein"):
            save.submit("empty-shift", replace(SHIFT, quantity=1))
        save.advance(days=7)
        end = save.summary()["village"]["mining"]
        self.assertEqual(end["ore_extracted"], 2)
        self.assertEqual(end["ore_at_market"], 2)

    def test_extraction_and_delivery_check_actor_route_and_time(self) -> None:
        save = self.create("access")
        with self.assertRaisesRegex(WorldError, "only the miner"):
            save.submit("farmer-shift", replace(SHIFT, actor=FARM_OWNER))
        with self.assertRaisesRegex(WorldError, "shift duration"):
            save.submit("instant-shift", replace(SHIFT, duration=1))
        with self.assertRaisesRegex(WorldError, "between 1 and 3"):
            save.submit("overlarge-shift", replace(SHIFT, quantity=4))
        with self.assertRaisesRegex(WorldError, "this road takes 40"):
            save.submit("instant-delivery", replace(LOAD, duration=1))
        with self.assertRaisesRegex(WorldError, "insufficient available iron_ore"):
            save.submit("empty-delivery", LOAD)
        save.submit("shift", SHIFT)
        save.advance_to(SHIFT_MINUTES)
        save.submit("delivery", LOAD)
        save.advance_to(SHIFT_MINUTES + 40)
        with self.assertRaisesRegex(WorldError, "at the mine"):
            save.submit("remote-shift", SHIFT)

    def test_canceling_a_load_leaves_ore_at_the_mine_until_a_new_arrival(self) -> None:
        save = self.create("canceled-load")
        save.submit("shift", SHIFT)
        save.advance_to(SHIFT_MINUTES)
        save.submit("delivery", LOAD)
        save.advance(minutes=20)
        reopened = Save(save.path)
        report = reopened.summary()
        self.assertEqual(report["village"]["travel"]["in_transit"][MINER]["ore"], 3)
        self.assertEqual(report["village"]["mining"]["ore_at_market"], 0)
        reopened.cancel("delivery")
        balances = reopened.summary()["inventory"]
        self.assertEqual(balances[MINE_STOCK][IRON_ORE], 3)
        self.assertEqual(balances[stall(MINER)][IRON_ORE], 0)
        reopened.submit("second-delivery", LOAD)
        reopened.advance(minutes=39)
        self.assertEqual(reopened.summary()["village"]["mining"]["ore_at_market"], 0)
        reopened.advance(minutes=1)
        after = reopened.summary()["village"]["mining"]
        self.assertEqual(after["ore_at_mine"], 0)
        self.assertEqual(after["ore_at_market"], 3)
        self.assertEqual(after["ore_delivered"], 3)

    def test_mid_delivery_reload_matches_and_reconstructs_inventory(self) -> None:
        direct, split = self.create("direct"), self.create("split")
        split.advance_to(140)
        metrics = split.summary()["village"]["mining"]
        self.assertEqual(metrics["delivery_arrives_at"], 159)
        self.assertEqual(metrics["ore_at_market"], 0)
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
        self.assertEqual(report["village"]["coin_supply"], 72)
        self.assertEqual(stock[stall(MINER)][IRON_ORE], STALL_TARGET)
        self.assertEqual(stock[DEPOSIT][ORE_IN_VEIN], 120 - STALL_TARGET)
        self.assertTrue(any(event["kind"] == "harvest_completed" and event["payload"]["actor"] == MINER
                            for event in journal))

    def test_an_empty_deposit_keeps_the_stall_empty_while_the_village_runs(self) -> None:
        save = self.create("empty", Config(starting_ore_deposit=0))
        save.advance(days=7)
        report = save.summary()["village"]
        self.assertEqual(report["mining"]["ore_extracted"], 0)
        self.assertEqual(report["mining"]["ore_delivered"], 0)
        self.assertEqual(report["mining"]["ore_at_market"], 0)
        self.assertEqual(report["charcoal"]["charcoal_in_stock"], 4)
        self.assertGreater(report["grain_eaten"], 0)
        self.assertEqual(report["coin_supply"], 72)

    def test_cli_shows_ore_arrival_and_keeps_the_earlier_charcoal_digest(self) -> None:
        result = test_lab.LabTests.run_cli("scenario", "mining", "--seed", "8", "--minutes", "160", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["village"]["mining"]
        self.assertEqual(report["deposit_remaining"], 117)
        self.assertEqual(report["ore_at_market"], 3)
        prior = test_lab.LabTests.run_cli("scenario", "charcoal", "--seed", "8", "--days", "1", "--json")
        self.assertEqual(prior.returncode, 0, prior.stderr)
        self.assertEqual(json.loads(prior.stdout)["digest"],
                         "d402b2da411d1fe5aff214b82f6beddd2f7a165ce1c0fe557aeefb6bb2d0939e")
