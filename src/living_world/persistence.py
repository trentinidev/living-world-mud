"""SQLite save files and transactional simulation operations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from collections import Counter
from contextlib import closing, contextmanager
from hashlib import sha256
from pathlib import Path
from typing import TypeVar

from . import contracts, market, routes
from .model import (
    CIVILIAN_CONTENT_VERSIONS, COIN, CONTRACTS_CONTENT_VERSIONS, IRON_HAMMER, IRON_HOE, MARKET_CONTENT_VERSIONS,
    MAX_CLOCK, VILLAGE_CONTENT_VERSIONS,
    Action, Config, Intent, World, WorldError,
    canonical_json, integer,
)
from .observability import village_metrics
from .simulation import Simulation

APPLICATION_ID = 0x4C574D55
MIGRATIONS = (
    (
        """CREATE TABLE world (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            snapshot TEXT NOT NULL
        )""",
        """CREATE TABLE journal (
            id INTEGER PRIMARY KEY,
            minute INTEGER NOT NULL CHECK (minute >= 0),
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            cause_id INTEGER REFERENCES journal(id) CHECK (cause_id < id)
        )""",
    ),
)
T = TypeVar("T")


class Save:
    """An authoritative save. Each successful mutation commits state and events together."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def create(
        cls, path: Path, seed: int, config: Config | None = None, *, scenario: str = "lab",
        player_name: str | None = None,
    ) -> Save:
        sim = Simulation.create(
            seed, config if config is not None else Config(), scenario, player_name=player_name,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb"):
            pass
        save = cls(path)
        with save.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            save.migrate(db, 0)
            db.execute("INSERT INTO world VALUES (1, ?)", (canonical_json(sim.world.snapshot()),))
            save.append_events(db, sim)
        return save

    @contextmanager
    def connect(self, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        uri = self.path.resolve().as_uri()
        mode = "ro" if readonly else "rw"
        with closing(sqlite3.connect(f"{uri}?mode={mode}", uri=True)) as db:
            db.execute("PRAGMA foreign_keys = ON")
            yield db

    @staticmethod
    def migrate(db: sqlite3.Connection, version: int) -> None:
        for next_version, statements in enumerate(MIGRATIONS[version:], start=version + 1):
            for statement in statements:
                db.execute(statement)
            db.execute(f"PRAGMA user_version = {next_version}")

    @staticmethod
    def load_world(db: sqlite3.Connection) -> World:
        if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise WorldError("file is not a Living World save")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if not 1 <= version <= len(MIGRATIONS):
            raise WorldError(f"unsupported save schema version {version}")
        row = db.execute("SELECT snapshot FROM world WHERE id = 1").fetchone()
        if row is None:
            raise WorldError("save has no world snapshot")
        try:
            return World.restore(json.loads(row[0]))
        except (TypeError, KeyError, json.JSONDecodeError) as error:
            raise WorldError("invalid world snapshot") from error

    @staticmethod
    def append_events(db: sqlite3.Connection, sim: Simulation) -> None:
        db.executemany(
            "INSERT INTO journal (id, minute, kind, payload, cause_id) VALUES (?, ?, ?, ?, ?)",
            ((event.id, event.minute, event.kind, canonical_json(event.payload), event.cause_id)
             for event in sim.events),
        )

    def mutate(self, operation: Callable[[Simulation], T]) -> T:
        with self.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            sim = Simulation(self.load_world(db))
            result = operation(sim)
            self.append_events(db, sim)
            db.execute("UPDATE world SET snapshot = ? WHERE id = 1",
                       (canonical_json(sim.world.snapshot()),))
        return result

    def read(self, operation: Callable[[Simulation], T]) -> T:
        with self.connect(readonly=True) as db, db:
            db.execute("BEGIN")
            return operation(Simulation(self.load_world(db)))

    def submit(self, key: str, intent: Intent) -> Action:
        return self.mutate(lambda sim: sim.submit(key, intent))

    def cancel(self, key: str) -> Action:
        return self.mutate(lambda sim: sim.cancel(key))

    def market_shock(self, shock: market.MarketShock) -> None:
        self.mutate(lambda sim: sim.market_shock(shock))

    def advance_to(self, minute: int) -> None:
        self.mutate(lambda sim: sim.advance_to(minute))

    def advance(self, *, minutes: int = 0, days: int = 0) -> None:
        def advance_relative(sim: Simulation) -> None:
            integer("minutes", minutes, 0, MAX_CLOCK)
            integer("days", days, 0, MAX_CLOCK)
            sim.advance_to(sim.world.minute + minutes + days * sim.world.config.minutes_per_day)

        self.mutate(advance_relative)

    def inspect(self, *, journal: bool = False) -> dict[str, object]:
        with self.connect(readonly=True) as db, db:
            db.execute("BEGIN")
            state = self.load_world(db)
            snapshot = state.snapshot()
            report: dict[str, object] = {
                "schema_version": db.execute("PRAGMA user_version").fetchone()[0],
                "digest": sha256(canonical_json(snapshot).encode("utf-8")).hexdigest(),
                "snapshot": snapshot,
            }
            if journal:
                report["journal"] = [
                    dict(id=event_id, minute=minute, kind=kind, payload=json.loads(payload),
                         cause_id=cause)
                    for event_id, minute, kind, payload, cause in db.execute(
                        "SELECT id, minute, kind, payload, cause_id FROM journal ORDER BY id"
                    )
                ]
            return report

    def summary(self) -> dict[str, object]:
        with self.connect(readonly=True) as db, db:
            db.execute("BEGIN")
            state = self.load_world(db)
            summary: dict[str, object] = {
                "minute": state.minute,
                "seed": state.seed,
                "content_version": state.content_version,
                "actors": len(state.actors),
                "pending_events": len(state.queue),
                "event_count": state.next_event_id - 1,
                "inventory": state.inventory,
                "digest": sha256(canonical_json(state.snapshot()).encode("utf-8")).hexdigest(),
            }
            if state.content_version in VILLAGE_CONTENT_VERSIONS:
                events = ((minute, kind, json.loads(payload)) for minute, kind, payload in
                          db.execute("SELECT minute, kind, payload FROM journal ORDER BY id"))
                available = None
                if state.content_version in MARKET_CONTENT_VERSIONS:
                    available = Simulation(state).available
                summary["village"] = village_metrics(state, events, available)
            return summary

    def audit_inventory(self) -> None:
        """Rebuild balances from the journal and raise on the first discrepancy."""
        with self.connect(readonly=True) as db, db:
            db.execute("BEGIN")
            state = self.load_world(db)
            events = db.execute("SELECT id, minute, kind, payload, cause_id FROM journal ORDER BY id")
            first = events.fetchone()
            if first is None or (first[0], first[1], first[2], first[4]) != (1, 0, "world_initialized", None):
                raise WorldError("journal is missing its initialization event")
            stock = json.loads(first[3])["inventory"]
            if any(quantity < 0 for account in stock.values() for quantity in account.values()):
                raise WorldError("journal initialization contains negative stock")
            last_id, last_minute = 1, 0
            for event_id, minute, _, payload, cause_id in events:
                if (event_id != last_id + 1 or not last_minute <= minute <= state.minute
                        or (cause_id is not None and not 1 <= cause_id <= last_id)):
                    raise WorldError(f"journal event {event_id} has an invalid order or cause")
                last_id, last_minute = event_id, minute
                for move in json.loads(payload).get("movements", ()):
                    source, destination = move["source"], move["destination"]
                    good, quantity = move["good"], move["quantity"]
                    if (type(quantity) is not int or quantity <= 0
                            or (source is None and destination is None)
                            or (good == COIN and (source is None or destination is None))):
                        raise WorldError(f"journal event {event_id} has an invalid movement")
                    if source is not None:
                        if source not in stock or stock[source].get(good, 0) < quantity:
                            raise WorldError(f"journal event {event_id} overdraws {good} from {source}")
                        stock[source][good] -= quantity
                    if destination is not None:
                        if destination not in stock:
                            raise WorldError(f"journal event {event_id} has an unknown destination")
                        target = stock[destination]
                        target[good] = target.get(good, 0) + quantity
            if last_id != state.next_event_id - 1 or state.inventory != stock:
                raise WorldError("journal inventory does not match the saved state")
            if state.content_version in CIVILIAN_CONTENT_VERSIONS:
                for good, records in ((IRON_HOE, state.crafted_hoes), (IRON_HAMMER, state.crafted_hammers)):
                    crafted = Counter(record.account for record in records.values())
                    physical = Counter({owner: account[good] for owner, account in stock.items() if account.get(good)})
                    if crafted != physical:
                        raise WorldError(f"{good} provenance does not match the saved balances")
            if state.content_version in CONTRACTS_CONTENT_VERSIONS:
                open_orders = Counter(order.farm for order in state.hoe_orders.values()
                                      if order.status in contracts.OPEN_STATUSES)
                for farm in routes.fields_for(state):
                    if open_orders[farm] > 1 or stock[contracts.escrow(farm)][COIN] != open_orders[farm] * contracts.PRICE:
                        raise WorldError(f"order escrow does not match the open orders for {farm}")
