import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from living_world.model import COIN, FARM_OWNER, SEED_GRAIN, Config, SeedIntent, WorldError
from living_world.persistence import Save
from living_world.routes import FIELDS, WEST_FARM, pantry


class SeedTradeTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_purchase_reserves_seed_and_coins_and_cancellation_releases_both(self):
        save = Save.create(self.directory / "trade.db", 8, Config(), scenario="seed-trade")
        purchase = SeedIntent("buy_seed", FARM_OWNER, 8, WEST_FARM)
        with self.assertRaisesRegex(WorldError, "at the seller"):
            save.submit("remote", purchase)

        def stage(sim):
            world = sim.world
            world.queue.clear()
            world.actors[FARM_OWNER] = replace(world.actors[FARM_OWNER], location=FIELDS[WEST_FARM])
            world.inventory[pantry(WEST_FARM)][SEED_GRAIN] = 4
            world.inventory[FARM_OWNER][COIN] = 1

        save.mutate(stage)
        with self.assertRaisesRegex(WorldError, "no surplus"):
            save.submit("protected", purchase)
        save.mutate(lambda sim: sim.world.inventory[pantry(WEST_FARM)].update({SEED_GRAIN: 5}))
        with self.assertRaisesRegex(WorldError, "insufficient available coin"):
            save.submit("unfunded", purchase)
        save.mutate(lambda sim: sim.world.inventory[FARM_OWNER].update({COIN: 2}))
        save.submit("held", purchase)
        start = save.inspect(journal=True)["journal"][-1]
        self.assertEqual([part["quantity"] for part in start["payload"]["reservations"]], [1, 2])
        save.cancel("held")
        save.submit("retry", purchase)
        Save(save.path).advance(minutes=8)
        inventory = save.summary()["inventory"]
        self.assertEqual(inventory[FARM_OWNER][SEED_GRAIN], 1)
        self.assertEqual(inventory[pantry(WEST_FARM)][SEED_GRAIN], 4)
        self.assertEqual(inventory[FARM_OWNER][COIN], 0)
        self.assertEqual(inventory[WEST_FARM][COIN], 20)

    def test_shortage_recovery_includes_travel_unloading_and_new_harvest(self):
        def recover(name, split):
            save = Save.create(self.directory / f"{name}.db", 8, Config(), scenario="seed-trade")
            save.advance(days=1)
            save.market_shock("seed-shortage")
            if split:
                save.advance(minutes=90)
                save = Save(save.path)
            save.advance_to(7 * 1440)
            return save

        save = recover("direct", False)
        observed = save.inspect(journal=True)
        self.assertEqual(recover("split", True).inspect(journal=True), observed)
        journal = observed["journal"]
        bought = next(event for event in journal if event["kind"] == "buy_seed_completed")
        unloaded = next(event for event in journal if event["kind"] == "store_seed_completed")
        self.assertEqual(bought["payload"]["location"], FIELDS[WEST_FARM])
        self.assertEqual(unloaded["payload"]["location"], FIELDS[FARM_OWNER])
        self.assertGreaterEqual(unloaded["minute"] - bought["minute"], 66)
        self.assertTrue(any(event["kind"] == "harvest_completed" and event["minute"] > unloaded["minute"]
                            and event["payload"]["farm"] == FARM_OWNER for event in journal))
        metrics = save.summary()["village"]
        self.assertEqual(metrics["seed_saving"]["seed_by_farm"][FARM_OWNER], 4)
        self.assertEqual(metrics["seed_trade"]["coins_paid_for_seed"], 2)
        self.assertEqual(metrics["coin_supply"], 156)
