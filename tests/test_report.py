import unittest

from living_world.cli import main
from living_world.model import Config, WorldError
from living_world.report import parse_seeds, viability_report


def without_runtime(report):
    report = dict(report, runtime_seconds=None)
    report["runs"] = [dict(run, runtime_seconds=None) for run in report["runs"]]
    return report


class ReportTests(unittest.TestCase):
    def test_baseline_seeds_are_functional_and_repeatable(self):
        first = viability_report("seed-trade", [0, 1], [1, 7], Config())
        self.assertEqual(first["functional_seeds"], 2)
        self.assertEqual(set(first["runs"][0]["horizons"]), {"1", "7"})
        self.assertEqual(first["runs"][0]["horizons"]["7"]["population"], 9)
        self.assertEqual(without_runtime(viability_report("seed-trade", [0, 1], [1, 7], Config())),
                         without_runtime(first))

    def test_a_village_without_seed_fails_the_production_check(self):
        config = Config.from_mapping({"village": {"starting_seed": 0}})
        report = viability_report("seed-saving", [3], [8], config)
        run = report["runs"][0]
        self.assertFalse(run["checks"]["recent_production"])
        self.assertTrue(run["checks"]["coin_conserved"])
        self.assertEqual(report["functional_seeds"], 0)

    def test_shock_is_applied_after_one_day(self):
        report = viability_report("seed-trade", [8], [7], Config(), "worker-loss")
        self.assertEqual(report["shock"], "worker-loss")
        self.assertTrue(report["runs"][0]["checks"]["coin_conserved"])

    def test_inputs_are_validated(self):
        self.assertEqual(parse_seeds("0-2,7"), [0, 1, 2, 7])
        self.assertEqual(parse_seeds("-3"), [-3])
        with self.assertRaisesRegex(WorldError, "market scenario"):
            viability_report("village", [0], [1], Config())
        with self.assertRaisesRegex(WorldError, "positive day horizons"):
            viability_report("seed-trade", [0], [0], Config())
        self.assertEqual(main(["report", "village", "--seeds", "0", "--days", "1"]), 1)


if __name__ == "__main__":
    unittest.main()
