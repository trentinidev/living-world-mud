"""Create, inspect, simulate, or play in a Living World save."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from .market import SHOCKS
from .model import Config, Transfer, WorldError
from .persistence import Save
from .player import play
from .report import parse_seeds, viability_report
from .web import serve

SCENARIOS = (
    "lab", "village", "market", "routes", "firewood", "charcoal", "mining", "smelting",
    "blacksmith", "tools", "seed-saving", "seed-trade", "hamlet", "civilian", "contracts", "apprenticeship",
)


def add_interval(parser: argparse.ArgumentParser, *, required: bool = True) -> None:
    interval = parser.add_mutually_exclusive_group(required=required)
    interval.add_argument("--minutes", type=int)
    interval.add_argument("--days", type=int)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="living-world", description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create a new SQLite world")
    create.add_argument("--save", type=Path, required=True)
    create.add_argument("--seed", type=int, required=True)
    create.add_argument("--scenario", choices=SCENARIOS, default="lab")
    create.add_argument("--config", type=Path, help="JSON overrides for world configuration")
    create.add_argument("--player", help="name a playable character in a new hamlet or career scenario")

    playable = commands.add_parser("play", help="open a hamlet save in the text interface")
    playable.add_argument("--save", type=Path, required=True)

    browser = commands.add_parser("web", help="play a local save in the browser")
    browser.add_argument("--save", type=Path, required=True)
    browser.add_argument("--port", type=int, default=8765, help="local port to listen on")
    browser.add_argument("--open", action="store_true", help="open the address in your default browser")

    simulate = commands.add_parser("simulate", help="advance an existing world")
    simulate.add_argument("--save", type=Path, required=True)
    simulate.add_argument("--headless", action="store_true", help="advance without a client")
    add_interval(simulate)

    inspect = commands.add_parser("inspect", help="read an existing save without advancing it")
    inspect.add_argument("--save", type=Path, required=True)
    display = inspect.add_mutually_exclusive_group()
    display.add_argument("--summary", action="store_true")
    display.add_argument("--journal", action="store_true")

    transfer = commands.add_parser("transfer", help="schedule a grain transfer")
    transfer.add_argument("--save", type=Path, required=True)
    transfer.add_argument("--id", required=True, help="stable action key")
    transfer.add_argument("--actor", required=True)
    transfer.add_argument("--target", required=True)
    transfer.add_argument("--quantity", type=int, required=True)
    transfer.add_argument("--duration", type=int, required=True)

    cancel = commands.add_parser("cancel", help="cancel a pending action")
    cancel.add_argument("--save", type=Path, required=True)
    cancel.add_argument("--id", required=True)

    scenario = commands.add_parser("scenario", help="run a scenario in a temporary save")
    scenario.add_argument("name", choices=SCENARIOS)
    scenario.add_argument("--seed", type=int, required=True)
    scenario.add_argument("--config", type=Path, help="JSON overrides for world configuration")
    scenario.add_argument("--json", action="store_true", help="output structured JSON (default)")
    scenario.add_argument("--shock", choices=SHOCKS, help="disrupt the market after one day")
    add_interval(scenario, required=False)

    report = commands.add_parser("report", help="run a zero-player viability report across seeds")
    report.add_argument("name", choices=SCENARIOS)
    report.add_argument("--seeds", type=parse_seeds, default=list(range(10)), help="e.g. 0-9 or 1,4,8")
    report.add_argument("--days", type=lambda text: [int(day) for day in text.split(",")],
                        default=[1, 7, 30, 90], help="comma-separated horizons, e.g. 1,7,30,90")
    report.add_argument("--config", type=Path, help="JSON overrides for world configuration")
    report.add_argument("--shock", choices=SHOCKS, help="disrupt the market after one day")
    report.add_argument("--json", action="store_true", help="output structured JSON (default)")
    return root


def get_config(path: Path | None) -> Config:
    return Config() if path is None else Config.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def dispatch(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "create":
        return Save.create(args.save, args.seed, get_config(args.config),
                           scenario=args.scenario, player_name=args.player).summary()
    if args.command == "report":
        return viability_report(args.name, args.seeds, args.days, get_config(args.config), args.shock)
    if args.command == "scenario":
        config = get_config(args.config)
        if args.shock and args.name in ("lab", "village"):
            raise WorldError("--shock requires a scenario with a market")
        with TemporaryDirectory(prefix="living-world-") as directory:
            save = Save.create(Path(directory) / "scenario.db", args.seed, config, scenario=args.name)
            minutes, days = args.minutes or 0, args.days or 0
            if args.name == "lab":
                save.submit("lab-transfer", Transfer("storekeeper", "neighbor", 2, 1))
                save.advance(minutes=30 if args.minutes is None and args.days is None else minutes,
                             days=days)
                return save.inspect(journal=True)
            if args.minutes is None and args.days is None:
                days = 7
            if args.shock:
                finish = minutes + days * config.minutes_per_day
                if finish <= config.minutes_per_day:
                    raise WorldError("a market shock needs a run longer than one simulated day")
                save.advance_to(config.minutes_per_day)
                save.market_shock(args.shock)
                save.advance_to(finish)
            else:
                save.advance(minutes=minutes, days=days)
            return save.summary()
    save = Save(args.save)
    if args.command == "simulate":
        save.advance(minutes=args.minutes or 0, days=args.days or 0)
        return save.summary()
    if args.command == "inspect":
        return save.summary() if args.summary else save.inspect(journal=args.journal)
    if args.command == "transfer":
        return asdict(save.submit(args.id, Transfer(args.actor, args.target, args.quantity, args.duration)))
    return asdict(save.cancel(args.id))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "play":
            play(Save(args.save))
            return 0
        if args.command == "web":
            serve(Save(args.save), args.port, open_browser=args.open)
            return 0
        result = dispatch(args)
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"living-world: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0
