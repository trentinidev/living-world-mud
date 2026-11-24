from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.farm_tools import HOE_BONUS, HOE_LIFETIME, HOE_PRICE, INSTALL_MINUTES
from living_world.model import (
    COIN, FARM_OWNER, GRAIN, IRON_HOE, SEED_GRAIN, Config, HoeHarvest, MarketIntent,
    ToolIntent, Travel, WorldError,
)
from living_world.persistence import Save
from living_world.routes import BLACKSMITH, FIELDS, MARKET_SQUARE, pantry, stall
from living_world.simulation import Simulation

FARM_STOCK = pantry(FARM_OWNER)
FIELD = FIELDS[FARM_OWNER]
HARVEST = MarketIntent("harvest", FARM_OWNER, 95, FARM_OWNER)
WITH_HOE = HoeHarvest("harvest", FARM_OWNER, 95, FARM_OWNER)
BUY_HOE = ToolIntent("buy_hoe", FARM_OWNER, 8, price=HOE_PRICE)
INSTALL = ToolIntent("install_hoe", FARM_OWNER, INSTALL_MINUTES)


class FarmToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, config: Config | None = None) -> Save:
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="tools")

    @staticmethod
    def stage_field(sim: Simulation, uses: int = 0) -> None:
        sim.world.queue.clear()
        sim.world.hoe_uses[FARM_OWNER] = uses
        sim.world.inventory[FARM_STOCK][IRON_HOE] = int(uses > 0)
        worker = sim.world.actors["farmhand-1"]
        sim.world.actors["farmhand-1"] = replace(worker, location=FIELD)

    def test_paired_harvests_use_the_same_seed_and_only_the_hoe_adds_grain(self) -> None:
        plain, equipped = self.create("plain"), self.create("equipped")
        plain.mutate(self.stage_field)
        equipped.mutate(lambda sim: self.stage_field(sim, HOE_LIFETIME))
        for save, intent in ((plain, HARVEST), (equipped, WITH_HOE)):
            save.submit("harvest", intent)
            save.advance_to(95)

        original, boosted = (save.summary() for save in (plain, equipped))
        self.assertEqual(original["inventory"][FARM_STOCK][SEED_GRAIN], 399)
        self.assertEqual(boosted["inventory"][FARM_STOCK][SEED_GRAIN], 399)
        self.assertEqual(boosted["inventory"][FARM_STOCK][GRAIN] - original["inventory"][FARM_STOCK][GRAIN],
                         HOE_BONUS)
        self.assertEqual(boosted["village"]["tools"]["remaining_uses_by_farm"][FARM_OWNER], HOE_LIFETIME - 1)
        self.assertEqual(boosted["village"]["tools"]["bonus_grain"], HOE_BONUS)

    def test_one_hoe_cannot_be_reserved_by_two_workers_and_cancellation_frees_it(self) -> None:
        save = self.create("exclusive")
        save.mutate(lambda sim: self.stage_field(sim, HOE_LIFETIME))
        worker = replace(WITH_HOE, actor="farmhand-1")
        save.submit("first", WITH_HOE)
        with self.assertRaisesRegex(WorldError, "hoe .* already reserved"):
            Save(save.path).submit("second", worker)
        save.cancel("first")
        save.submit("second", worker)
        save.submit("without-hoe", HARVEST)
        save.advance_to(95)
        report = save.summary()["village"]
        self.assertEqual(report["harvests"], 2)
        self.assertEqual(report["tools"]["assisted_harvests"], 1)
        self.assertEqual(report["tools"]["remaining_uses_by_farm"][FARM_OWNER], HOE_LIFETIME - 1)

    def test_last_use_retires_the_hoe_and_plain_farming_continues(self) -> None:
        save = self.create("wear")
        save.mutate(lambda sim: self.stage_field(sim, 1))
        save.submit("last-use", WITH_HOE)
        save.advance_to(95)
        report = save.summary()
        self.assertEqual(report["village"]["tools"]["hoes_worn_out"], 1)
        self.assertEqual(report["inventory"][FARM_STOCK][IRON_HOE], 0)
        with self.assertRaisesRegex(WorldError, "no usable hoe"):
            save.submit("broken", WITH_HOE)
        save.submit("plain", HARVEST)
        save.advance_to(190)
        self.assertEqual(save.summary()["village"]["tools"]["assisted_harvests"], 1)

    def test_farmers_pay_the_blacksmith_and_install_the_hoe_at_home(self) -> None:
        save = self.create("purchase")

        def stock_market(sim: Simulation) -> None:
            self.stage_field(sim)
            world = sim.world
            world.inventory[stall(BLACKSMITH)][IRON_HOE] = 1
            world.actors[FARM_OWNER] = replace(world.actors[FARM_OWNER], location=MARKET_SQUARE)

        save.mutate(stock_market)
        balances = save.summary()["inventory"]
        with self.assertRaisesRegex(WorldError, "costs 15"):
            save.submit("wrong-price", replace(BUY_HOE, price=14))
        save.submit("buy", BUY_HOE)
        save.advance_to(8)
        inventory = save.summary()["inventory"]
        self.assertEqual(inventory[FARM_OWNER][COIN], balances[FARM_OWNER][COIN] - HOE_PRICE)
        self.assertEqual(inventory[BLACKSMITH][COIN], balances[BLACKSMITH][COIN] + HOE_PRICE)
        self.assertEqual(inventory[FARM_OWNER][IRON_HOE], 1)
        self.assertEqual(inventory[FARM_STOCK][IRON_HOE], 0)
        with self.assertRaisesRegex(WorldError, "installed at the buyer's farm"):
            save.submit("remote-install", INSTALL)
        save.submit("return", Travel(FARM_OWNER, MARKET_SQUARE, FIELD, 20))
        save.advance_to(28)
        save.submit("install", INSTALL)
        save.advance_to(28 + INSTALL_MINUTES)
        report = save.summary()
        self.assertEqual(report["inventory"][FARM_OWNER][IRON_HOE], 0)
        self.assertEqual(report["inventory"][FARM_STOCK][IRON_HOE], 1)
        self.assertEqual(report["village"]["tools"]["remaining_uses_by_farm"][FARM_OWNER], HOE_LIFETIME)

    def test_autonomous_replacement_and_mid_harvest_save_reconcile_the_ledger(self) -> None:
        direct, split = self.create("direct"), self.create("split")
        end = 7 * 1440
        direct.advance_to(end)
        actual = direct.inspect(journal=True)
        first = next(event for event in actual["journal"] if "hoe_bonus_grain" in event["payload"])
        split.advance_to(first["minute"] - 1)
        self.assertTrue(any(action["status"] == "started" and action["intent"].get("with_hoe")
                            for action in split.inspect()["snapshot"]["actions"].values()))
        Save(split.path).advance_to(end)
        self.assertEqual(split.inspect(journal=True), actual)

        stock = actual["journal"][0]["payload"]["inventory"]
        for event in actual["journal"][1:]:
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
        self.assertEqual(report["village"]["coin_supply"], 156)
        tools = report["village"]["tools"]
        self.assertGreater(tools["replacement_hoes_installed"], 0)
        self.assertEqual(tools["assisted_harvests"] + sum(tools["remaining_uses_by_farm"].values()),
                         tools["hoes_installed"] * HOE_LIFETIME)
        self.assertEqual(tools["bonus_grain"], tools["assisted_harvests"] * HOE_BONUS)

    def test_without_ore_farms_fall_back_to_plain_harvests(self) -> None:
        save = self.create("no-ore", Config(starting_ore_deposit=0))
        save.advance(days=7)
        village = save.summary()["village"]
        self.assertEqual(village["tools"]["hoes_bought"], 0)
        self.assertEqual(village["tools"]["assisted_harvests"], 0)
        self.assertGreater(village["harvests"], 0)

    def test_cli_reports_tool_use_and_preserves_the_blacksmith_digest(self) -> None:
        result = test_lab.LabTests.run_cli("scenario", "tools", "--seed", "8", "--days", "1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        tools = json.loads(result.stdout)["village"]["tools"]
        self.assertEqual(tools["hoes_installed"], 1)
        self.assertEqual(tools["assisted_harvests"], 1)
        self.assertEqual(tools["bonus_grain"], 2)
        prior = test_lab.LabTests.run_cli("scenario", "blacksmith", "--seed", "8", "--minutes", "1040", "--json")
        self.assertEqual(prior.returncode, 0, prior.stderr)
        self.assertEqual(json.loads(prior.stdout)["digest"],
                         "a07251cec0b8e9a1ffb37a0e49086b691de2572f41e295a904144f762c7e3aa8")
