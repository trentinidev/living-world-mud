"""Multi-seed viability report for zero-player village runs.

Wall-clock runtime is measured for the report only. It never feeds back into the simulation.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from .market import MarketShock
from .model import Config, WorldError
from .persistence import Save
from .simulation import Simulation

RECENT_DAYS = 7
MAX_CAPPED_HUNGER_SHARE = 0.1
COUNTERS = ("harvests", "purchases", "grain_produced", "grain_eaten", "coin_paid_in_wages",
            "coin_paid_for_food", "failed_actions", "rests", "waits")


def snapshot(save: Save, settings_cap: int) -> dict[str, object]:
    summary = save.summary()
    village = summary["village"]
    hunger = [need["hunger"] for need in village["needs"].values()]
    goods: Counter[str] = Counter()
    for inventory in summary["inventory"].values():
        goods.update(inventory)
    result: dict[str, object] = {key: village[key] for key in COUNTERS}
    result.update(
        population=len(hunger),
        available_farmhands=village["market"]["available_farmhands"],
        coin_supply=village["coin_supply"],
        grain_in_stock=village["grain_in_stock"],
        mean_hunger=round(sum(hunger) / len(hunger), 1),
        max_hunger=max(hunger),
        capped_hunger=sum(value >= settings_cap for value in hunger),
        stock_by_good=dict(goods),
        market=village["market"],
    )
    for section in ("forestry", "charcoal", "mining", "smelting", "blacksmith", "tools", "seed_saving",
                    "seed_trade", "employment"):
        if section in village:
            result[section] = village[section]
    if "seed_saving" in village:
        result["seed_by_farm"] = village["seed_saving"]["seed_by_farm"]
    return result


def advance_days(save: Save, days: int) -> None:
    if days == 0:
        return

    def advance(sim: Simulation) -> None:
        minutes = sim.world.config.minutes_per_day
        for _ in range(days):
            sim.advance_to(sim.world.minute + minutes)

    # Keep the per-day event budget while writing the checkpoint only once.
    save.mutate(advance)


def run_seed(directory: Path, scenario: str, seed: int, config: Config, horizons: list[int],
             shock: MarketShock | None) -> dict[str, object]:
    started = time.perf_counter()
    save = Save.create(directory / f"{scenario}-{seed}.db", seed, config, scenario=scenario)
    initial_coin = save.summary()["village"]["coin_supply"]
    final = horizons[-1]
    checkpoints = sorted(set(horizons) | ({final - RECENT_DAYS} if final > RECENT_DAYS else set()))
    snapshots: dict[int, dict[str, object]] = {}
    done = 0
    for day in checkpoints:
        if shock and done < 1 <= day:
            advance_days(save, 1 - done)
            done = 1
            save.market_shock(shock)
        advance_days(save, day - done)
        done = day
        snapshots[day] = snapshot(save, 3 * config.village.meal_relief)
    end = snapshots[final]
    start = snapshots.get(final - RECENT_DAYS, {key: 0 for key in COUNTERS})
    recent = {key: end[key] - start[key] for key in ("harvests", "purchases", "grain_eaten")}
    audit_error = None
    try:
        save.audit_inventory()
    except WorldError as error:
        audit_error = str(error)
    checks = {
        "journal_balanced": audit_error is None,
        "coin_conserved": all(snap["coin_supply"] == initial_coin for snap in snapshots.values()),
        "no_failed_actions": end["failed_actions"] == 0,
        "recent_production": recent["harvests"] > 0,
        "recent_trade": recent["purchases"] > 0,
        "recent_consumption": recent["grain_eaten"] > 0,
        "food_in_stock": end["grain_in_stock"] > 0,
        "hunger_within_bounds": end["capped_hunger"] <= MAX_CAPPED_HUNGER_SHARE * end["population"],
    }
    return {
        "seed": seed,
        "horizons": {str(day): snapshots[day] for day in horizons},
        f"last_{RECENT_DAYS}_days": recent,
        "checks": checks,
        "audit_error": audit_error,
        "functional": all(checks.values()),
        "runtime_seconds": round(time.perf_counter() - started, 2),
    }


def viability_report(scenario: str, seeds: list[int], horizons: list[int], config: Config,
                     shock: MarketShock | None = None) -> dict[str, object]:
    if scenario in ("lab", "village"):
        raise WorldError("the viability report requires a market scenario")
    if not seeds or not horizons or min(horizons) < 1:
        raise WorldError("the report needs at least one seed and positive day horizons")
    horizons = sorted(set(horizons))
    if shock and horizons[-1] <= 1:
        raise WorldError("a market shock needs a run longer than one simulated day")
    started = time.perf_counter()
    with TemporaryDirectory(prefix="living-world-report-") as directory:
        runs = [run_seed(Path(directory), scenario, seed, config, horizons, shock) for seed in seeds]
    functional = sum(run["functional"] for run in runs)
    return {
        "scenario": scenario,
        "shock": shock,
        "horizons": horizons,
        "criteria": {
            "journal_balanced": "replaying the causal journal yields the saved stocks and accounts",
            "coin_conserved": "coin supply equals the initialized supply at every horizon",
            "no_failed_actions": "no started action failed at completion",
            "recent_production": f"at least one harvest in the last {RECENT_DAYS} simulated days",
            "recent_trade": f"at least one food purchase in the last {RECENT_DAYS} simulated days",
            "recent_consumption": f"grain eaten in the last {RECENT_DAYS} simulated days",
            "food_in_stock": "at least one unit of edible grain in the village at the final horizon",
            "hunger_within_bounds": f"at most {MAX_CAPPED_HUNGER_SHARE:.0%} of NPCs at the hunger cap",
        },
        "functional_seeds": functional,
        "seed_count": len(runs),
        "runs": runs,
        "runtime_seconds": round(time.perf_counter() - started, 2),
    }


def parse_seeds(text: str) -> list[int]:
    seeds: list[int] = []
    for part in text.split(","):
        if "-" in part.strip()[1:]:
            low, high = part.rsplit("-", 1)
            seeds.extend(range(int(low), int(high) + 1))
        else:
            seeds.append(int(part))
    return seeds
