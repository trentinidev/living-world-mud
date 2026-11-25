import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from shutil import copyfile

from living_world import blacksmith
from living_world.model import COIN, IRON_HAMMER, Config, ForgeIntent, Travel, WorldError
from living_world.persistence import Save
from living_world.player import execute
from living_world.routes import BLACKSMITH, FORGE, MARKET_SQUARE


class ApprenticeshipTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def arrive(self, case, config=None):
        save = Save.create(self.directory / f"{case}.db", 8, config, scenario="apprenticeship",
                           player_name="Iara")
        execute(save, "go market-square")
        execute(save, "go forge")
        return save

    def test_timed_lesson_holds_the_fee_and_mentor_then_persists_the_recipe(self):
        save = self.arrive("lesson")
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "learn the hammer recipe"):
            execute(save, "craft hammer")
        self.assertEqual(save.inspect(journal=True), before)

        save.submit("lesson", ForgeIntent("learn_hammer", "player", blacksmith.HAMMER_LESSON_MINUTES))
        self.assertEqual(save.read(lambda sim: sim.available("player", COIN)), 1)
        self.assertFalse(save.read(lambda sim: sim.forge_open()))
        with self.assertRaisesRegex(WorldError, "already busy"):
            save.submit("leave", Travel(BLACKSMITH, FORGE, MARKET_SQUARE, 15))

        save.advance(minutes=59)
        self.assertNotIn("hoe, hammer", execute(save, "skills"))
        save = Save(save.path)
        save.advance(minutes=1)
        self.assertIn("Recipes: hoe, hammer", execute(save, "skills"))
        self.assertIn("0 XP", execute(save, "skills"))
        self.assertEqual(save.summary()["village"]["apprenticeship"]["coins_paid_for_lessons"], 2)
        self.assertIn("coin: 1", execute(save, "inventory"))
        with self.assertRaisesRegex(WorldError, "already know"):
            execute(save, "learn hammer")
        save.audit_inventory()

    def test_lesson_requires_funds_and_cancellation_releases_both_participants(self):
        config = Config.from_mapping({"village": {"starting_hand_coin": 0}})
        empty = self.arrive("unfunded", config)
        before = empty.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "insufficient available coin"):
            execute(empty, "learn hammer")
        self.assertEqual(empty.inspect(journal=True), before)

        save = self.arrive("canceled")
        save.submit("lesson", ForgeIntent("learn_hammer", "player", blacksmith.HAMMER_LESSON_MINUTES))
        save.cancel("lesson")
        self.assertEqual(save.read(lambda sim: sim.available("player", COIN)), 3)
        self.assertTrue(save.read(lambda sim: sim.forge_open()))
        self.assertNotIn("hoe, hammer", execute(save, "skills"))
        save.submit("leave", Travel(BLACKSMITH, FORGE, MARKET_SQUARE, 15))
        save.audit_inventory()

    def test_crafted_hammer_improves_quality_and_wears_out(self):
        save = self.arrive("hammer")
        for command in (
            "learn hammer", "go market-square", "go east-farm", "work", "work", "rest", "wait 120",
            "work", "work", "rest", "wait 180", "work", "work", "rest", "wait 180", "work", "rest",
            "go market-square", "wait 24", "buy iron", "buy firewood", "go forge", "craft hammer",
        ):
            execute(save, command)
        key, record = save.read(lambda sim: next(iter(sim.world.crafted_hammers.items())))
        self.assertEqual(record.maker, "player")
        self.assertEqual(record.quality, 64)
        self.assertEqual(record.uses_left, 6)
        save.audit_inventory()

        last_use = Save(self.directory / "last-use.db")
        copyfile(save.path, last_use.path)
        last_use.mutate(lambda sim: sim.world.crafted_hammers.update({key: replace(record, uses_left=1)}))
        for replay in (Save(save.path), last_use):
            execute(replay, "wait 219")
            self.assertIn("Your hammer added 6 quality", execute(replay, "work"))
            self.assertIn("2 XP", execute(replay, "skills"))
            replay.audit_inventory()
        first_use = save.inspect()["snapshot"]["crafted_hammers"][key]
        self.assertEqual(first_use["uses_left"], 5)
        retired = last_use.inspect()["snapshot"]
        self.assertNotIn(key, retired["crafted_hammers"])
        self.assertEqual(retired["inventory"]["player"][IRON_HAMMER], 0)
        self.assertEqual(last_use.summary()["village"]["apprenticeship"]["hammers_retired"], 1)
