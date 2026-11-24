from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_lab
from living_world.blacksmith import FORGE_MINUTES, IRON_PRICE, TOOL_STOCK
from living_world.model import COIN, IRON, IRON_HOE, Config, ForgeIntent, Travel, WorldError
from living_world.persistence import Save
from living_world.routes import BLACKSMITH, FORGE, MARKET_SQUARE, SMELTER, stall
from living_world.simulation import Simulation

HOE = ForgeIntent("forge_hoe", BLACKSMITH, FORGE_MINUTES)


class BlacksmithTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = Path(directory)

    def create(self, name: str, config: Config | None = None) -> Save:
        return Save.create(self.directory / f"{name}.db", 8, config, scenario="blacksmith")

    def test_forging_requires_iron_the_blacksmith_and_the_forge(self) -> None:
        save = self.create("access")
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "insufficient available iron"):
            save.submit("no-iron", HOE)
        with self.assertRaisesRegex(WorldError, "only the blacksmith"):
            save.submit("other-worker", replace(HOE, actor="farmhand-1"))
        with self.assertRaisesRegex(WorldError, "forging duration"):
            save.submit("instant", replace(HOE, duration=1))
        self.assertEqual(save.inspect(journal=True), before)
        save.submit("walk", Travel(BLACKSMITH, FORGE, MARKET_SQUARE, 15))
        save.advance_to(15)
        with self.assertRaisesRegex(WorldError, "at the forge"):
            save.submit("remote-forge", HOE)

    def test_iron_purchase_reserves_the_last_unit_and_pays_the_smelter(self) -> None:
        save = self.create("purchase")

        def stock_market(sim: Simulation) -> None:
            world = sim.world
            world.actors[BLACKSMITH] = replace(world.actors[BLACKSMITH], location=MARKET_SQUARE)
            world.inventory[stall(SMELTER)][IRON] = 1
            world.inventory[BLACKSMITH][COIN] = IRON_PRICE
            world.queue.clear()

        save.mutate(stock_market)
        purchase = ForgeIntent("buy_iron", BLACKSMITH, 8, price=IRON_PRICE)
        before = save.summary()["inventory"]
        with self.assertRaisesRegex(WorldError, "costs 12"):
            save.submit("stale-quote", replace(purchase, price=11))
        with self.assertRaisesRegex(WorldError, "insufficient available coin"):
            save.submit("unfunded", replace(purchase, actor="farmhand-1"))
        save.submit("buy", purchase)
        with self.assertRaisesRegex(WorldError, "insufficient available iron"):
            save.submit("competing", replace(purchase, actor="farmhand-2"))
        save.advance(minutes=8)
        after = save.summary()["inventory"]
        self.assertEqual(after[BLACKSMITH][COIN], 0)
        self.assertEqual(after[SMELTER][COIN] - before[SMELTER][COIN], IRON_PRICE)
        self.assertEqual(after[BLACKSMITH][IRON], 1)
        self.assertEqual(after[stall(SMELTER)][IRON], 0)

    def test_iron_is_stocked_at_the_market_only_when_delivery_finishes(self) -> None:
        delivered = self.create("delivered")
        delivered.advance_to(850)
        first = next(event for event in delivered.inspect(journal=True)["journal"]
                     if event["kind"] == "travel_completed"
                     and any(move["good"] == IRON for move in event["payload"]["movements"]))
        pending = self.create("road")
        pending.advance_to(first["minute"] - 1)
        report = pending.summary()["village"]
        self.assertEqual(report["travel"]["in_transit"][SMELTER]["iron"], 1)
        self.assertEqual(report["blacksmith"]["iron_at_market"], 0)
        pending.advance_to(first["minute"])
        self.assertEqual(pending.summary()["village"]["blacksmith"]["iron_at_market"], 1)

    def test_canceling_and_retrying_forging_consumes_the_reserved_iron_once(self) -> None:
        save = self.create("cancellation")
        save.advance_to(950)
        actions = save.inspect()["snapshot"]["actions"]
        key = next(key for key, action in actions.items()
                   if action["status"] == "started" and action["intent"].get("kind") == "forge_hoe")
        save.cancel(key)
        before = save.summary()["inventory"]
        self.assertEqual(before[BLACKSMITH][IRON], 1)
        self.assertEqual(before[TOOL_STOCK][IRON_HOE], 0)
        save.submit("retry", HOE)
        Save(save.path).advance(minutes=FORGE_MINUTES - 1)
        self.assertEqual(save.summary()["village"]["blacksmith"]["hoes_in_stock"], 0)
        save.advance(minutes=1)
        self.assertEqual(save.submit("retry", HOE).status, "completed")
        after = save.summary()["inventory"]
        self.assertEqual(after[BLACKSMITH][IRON], 0)
        self.assertEqual(after[TOOL_STOCK][IRON_HOE], 1)

    def test_shortage_prevents_iron_purchases_and_tool_production(self) -> None:
        save = self.create("empty-ore", Config(starting_ore_deposit=0))
        save.advance(days=7)
        village = save.summary()["village"]
        self.assertEqual(village["smelting"]["iron_produced"], 0)
        self.assertEqual(village["blacksmith"]["iron_purchased"], 0)
        self.assertEqual(village["blacksmith"]["hoes_forged"], 0)
        self.assertIsNone(village["blacksmith"]["forge_finishes_at"])
        self.assertEqual(village["coin_supply"], 156)

    def test_mid_forge_save_replays_and_journal_reconstructs_every_balance(self) -> None:
        direct, split = self.create("direct"), self.create("split")
        split.advance_to(950)
        waiting = split.summary()["village"]["blacksmith"]
        self.assertEqual(waiting["forge_finishes_at"], 1040)
        self.assertEqual(waiting["hoes_in_stock"], 0)
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
        self.assertEqual(report["village"]["blacksmith"]["coins_paid_to_smelter"], 36)
        self.assertEqual(report["village"]["coin_supply"], 156)
        self.assertEqual(stock[TOOL_STOCK][IRON_HOE], 3)

    def test_cli_reports_the_first_hoe_and_preserves_the_smelting_digest(self) -> None:
        result = test_lab.LabTests.run_cli("scenario", "blacksmith", "--seed", "8", "--minutes", "1040", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["village"]["blacksmith"]
        self.assertEqual(report["coins_paid_to_smelter"], IRON_PRICE)
        self.assertEqual(report["iron_consumed"], 1)
        self.assertEqual(report["hoes_in_stock"], 1)
        prior = test_lab.LabTests.run_cli("scenario", "smelting", "--seed", "8", "--minutes", "754", "--json")
        self.assertEqual(prior.returncode, 0, prior.stderr)
        self.assertEqual(json.loads(prior.stdout)["digest"],
                         "0501a15373e4a35b702e11c7ba3381e2bba7b8a5fa9ca83f9d4ef82a02b4a886")
