from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.model import (
    FARM_OWNER, GRAIN, IRON_HOE, SEED_GRAIN, Config, HoeHarvest, MarketIntent,
    VillageConfig, WorldError,
)
from living_world.persistence import Save
from living_world.routes import FIELDS, pantry
from living_world.simulation import Simulation

FARM_STOCK = pantry(FARM_OWNER)
SHIFT = MarketIntent("harvest", FARM_OWNER, 95, FARM_OWNER)


class SeedSavingTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, seed: int = 8, **settings: int) -> Save:
        config = Config(village=VillageConfig(**({"starting_seed": 1} | settings)))
        return Save.create(self.directory / f"{name}.db", seed, config, scenario="seed-saving")

    def test_same_harvest_divides_food_and_seed_without_changing_gross_yield(self) -> None:
        saved = self.create("saved", harvest_min=4, harvest_max=4)
        control = self.create("control", harvest_min=4, harvest_max=4, seed_reserve_target=0)
        for save in (saved, control):
            save.mutate(lambda sim: sim.world.queue.clear())
            save.submit("harvest", SHIFT)
            save.advance_to(95)
        with_saving, without = (save.summary()["village"]["seed_saving"] for save in (saved, control))
        self.assertEqual(with_saving["total_grain_harvested"], 4)
        self.assertEqual(without["total_grain_harvested"], 4)
        self.assertEqual(with_saving["food_grain_harvested"], 2)
        self.assertEqual(without["food_grain_harvested"], 4)
        self.assertEqual(with_saving["seed_by_farm"][FARM_OWNER], 2)
        self.assertEqual(without["seed_by_farm"][FARM_OWNER], 0)

    def test_reserve_stops_at_the_target_and_leaves_surplus_grain_for_meals(self) -> None:
        save = self.create("target", harvest_min=4, harvest_max=4)
        save.mutate(lambda sim: sim.world.queue.clear())
        for index in range(4):
            save.submit(f"harvest-{index}", SHIFT)
            save.advance(minutes=95)
        report = save.summary()["village"]["seed_saving"]
        self.assertEqual(report["seed_by_farm"][FARM_OWNER], 4)
        self.assertEqual(report["seeds_planted"], 4)
        self.assertEqual(report["seeds_saved"], 7)
        self.assertEqual(report["food_grain_harvested"], 9)

        full = self.create("full", starting_seed=6, harvest_min=4, harvest_max=4)
        full.mutate(lambda sim: sim.world.queue.clear())
        full.submit("harvest", SHIFT)
        full.advance(minutes=95)
        report = full.summary()["village"]["seed_saving"]
        self.assertEqual(report["seeds_saved"], 0)
        self.assertEqual(report["food_grain_harvested"], 4)

    def test_a_one_grain_harvest_leaves_food_and_cannot_replant_from_zero(self) -> None:
        with self.assertRaisesRegex(WorldError, "seed_reserve_target"):
            VillageConfig(seed_reserve_target=-1)
        save = self.create("single", harvest_min=1, harvest_max=1)
        save.mutate(lambda sim: sim.world.queue.clear())
        save.submit("harvest", SHIFT)
        save.advance_to(95)
        report = save.summary()["village"]["seed_saving"]
        self.assertEqual(report["food_grain_harvested"], 1)
        self.assertEqual(report["seeds_saved"], 0)
        with self.assertRaisesRegex(WorldError, "insufficient available seed_grain"):
            save.submit("out-of-seed", SHIFT)

    def test_hoed_harvest_partitions_the_bonus_crop_and_spends_one_tool_use(self) -> None:
        save = self.create("hoe", harvest_min=3, harvest_max=3)

        def install(sim: Simulation) -> None:
            sim.world.queue.clear()
            sim.world.inventory[FARM_STOCK][IRON_HOE] = 1
            sim.world.hoe_uses[FARM_OWNER] = 8

        save.mutate(install)
        save.submit("hoe-harvest", HoeHarvest("harvest", FARM_OWNER, 95, FARM_OWNER))
        save.advance_to(95)
        report = save.summary()["village"]
        self.assertEqual(report["seed_saving"]["total_grain_harvested"], 5)
        self.assertEqual(report["seed_saving"]["seeds_saved"], 2)
        self.assertEqual(report["seed_saving"]["food_grain_harvested"], 3)
        self.assertEqual(report["tools"]["remaining_uses_by_farm"][FARM_OWNER], 7)

    def test_two_simultaneous_shifts_refill_one_seed_bank_without_overfilling(self) -> None:
        save = self.create("simultaneous", starting_seed=2, harvest_min=4, harvest_max=4,
                           seed_reserve_target=3)

        def stage_worker(sim: Simulation) -> None:
            sim.world.queue.clear()
            worker = sim.world.actors["farmhand-1"]
            sim.world.actors["farmhand-1"] = replace(worker, location=FIELDS[FARM_OWNER])

        save.mutate(stage_worker)
        save.submit("owner", SHIFT)
        save.submit("worker", replace(SHIFT, actor="farmhand-1"))
        save.advance_to(95)
        report = save.summary()
        self.assertEqual(report["inventory"][FARM_STOCK][SEED_GRAIN], 3)
        self.assertEqual(report["village"]["seed_saving"]["seeds_saved"], 3)
        self.assertEqual(report["village"]["seed_saving"]["food_grain_harvested"], 5)

    def test_low_seed_farms_keep_planting_and_households_eat_more_across_seeds(self) -> None:
        for seed in (0, 8, 9):
            with self.subTest(seed=seed):
                saved = self.create(f"saved-{seed}", seed)
                control = self.create(f"control-{seed}", seed, seed_reserve_target=0)
                for save in (saved, control):
                    save.advance(days=7)
                renewed, exhausted = (save.summary()["village"] for save in (saved, control))
                self.assertGreater(renewed["seed_saving"]["seeds_planted"], 2)
                self.assertEqual(exhausted["seed_saving"]["seeds_planted"], 2)
                self.assertEqual(exhausted["seed_in_stock"], 0)
                self.assertGreater(renewed["grain_eaten"], exhausted["grain_eaten"])
                for farm in ("farm-owner", "west-farm-owner"):
                    self.assertLess(renewed["needs"][farm]["hunger"], exhausted["needs"][farm]["hunger"])
                self.assertEqual(renewed["coin_supply"], exhausted["coin_supply"])

    def test_reloading_during_harvest_preserves_both_outputs_and_the_journal(self) -> None:
        direct, split = self.create("direct"), self.create("split")
        direct.advance(days=7)
        expected = direct.inspect(journal=True)
        first = next(event for event in expected["journal"] if event["kind"] == "harvest_completed")
        split.advance_to(first["minute"] - 1)
        self.assertTrue(any(action["intent"].get("kind") == "harvest" and action["status"] == "started"
                            for action in split.inspect()["snapshot"]["actions"].values()))
        Save(split.path).advance_to(7 * 1440)
        self.assertEqual(split.inspect(journal=True), expected)

        stock = expected["journal"][0]["payload"]["inventory"]
        for event in expected["journal"][1:]:
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
        village = report["village"]
        seeds = village["seed_saving"]
        self.assertEqual(village["seed_in_stock"], 2 + seeds["seeds_saved"] - seeds["seeds_planted"])
        self.assertEqual(village["grain_in_stock"], 10 + seeds["food_grain_harvested"] - village["grain_eaten"])

    def test_cli_reads_low_seed_config_and_preserves_the_earlier_tools_digest(self) -> None:
        config = self.directory / "low.json"
        config.write_text('{"village":{"starting_seed":1}}', encoding="utf-8")
        result = test_lab.LabTests.run_cli("scenario", "seed-saving", "--seed", "8", "--days", "7",
                                           "--config", str(config), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["village"]
        self.assertEqual(report["seed_saving"]["seed_by_farm"], {"farm-owner": 4, "west-farm-owner": 4})
        self.assertEqual(report["grain_eaten"], 180)
        prior = test_lab.LabTests.run_cli("scenario", "tools", "--seed", "8", "--days", "7", "--json")
        self.assertEqual(prior.returncode, 0, prior.stderr)
        self.assertEqual(json.loads(prior.stdout)["digest"],
                         "6b9a9aae5eab9615721595d94d4ee597ff84df20f4c6d8848e7c261e05ca4bdc")
