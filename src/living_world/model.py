"""Versioned data shared by the simulation and its adapters."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import ClassVar, Literal, Self

RULES_VERSION = 1
LAB_CONTENT_VERSION = "lab-1"
VILLAGE_CONTENT_VERSION = "village-food-1"
MARKET_CONTENT_VERSION = "village-market-1"
ROUTES_CONTENT_VERSION = "village-routes-1"
FIREWOOD_CONTENT_VERSION = "village-firewood-1"
CHARCOAL_CONTENT_VERSION = "village-charcoal-1"
MINING_CONTENT_VERSION = "village-mining-1"
KILN_CONTENT_VERSIONS = (CHARCOAL_CONTENT_VERSION, MINING_CONTENT_VERSION)
FORESTRY_CONTENT_VERSIONS = (FIREWOOD_CONTENT_VERSION, *KILN_CONTENT_VERSIONS)
SPATIAL_CONTENT_VERSIONS = (ROUTES_CONTENT_VERSION, *FORESTRY_CONTENT_VERSIONS)
MARKET_CONTENT_VERSIONS = (MARKET_CONTENT_VERSION, *SPATIAL_CONTENT_VERSIONS)
VILLAGE_CONTENT_VERSIONS = (VILLAGE_CONTENT_VERSION, *MARKET_CONTENT_VERSIONS)
MAX_CLOCK = 2**63 - 1
MAX_QUANTITY = 1_000_000
GRAIN = "grain"
COIN = "coin"
SEED_GRAIN = "seed_grain"
STANDING_WOOD = "standing_wood"
FIREWOOD = "firewood"
CHARCOAL = "charcoal"
ORE_IN_VEIN = "ore_in_vein"
IRON_ORE = "iron_ore"
DEFAULT_STANDING_WOOD = 240
DEFAULT_ORE_DEPOSIT = 120
FARM_OWNER = "farm-owner"
FARMSTEAD = "alderwick-farm"


class WorldError(ValueError):
    """The world cannot accept a command or configuration."""


def integer(name: str, value: int, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise WorldError(f"{name} must be an integer between {minimum} and {maximum}")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_fields(cls: type, values: object) -> dict:
    if not isinstance(values, dict) or any(not isinstance(key, str) for key in values):
        raise WorldError("configuration must be a JSON object")
    unknown = sorted(values.keys() - {item.name for item in fields(cls)})
    if unknown:
        raise WorldError(f"unknown configuration fields: {', '.join(unknown)}")
    return values


@dataclass(frozen=True, slots=True)
class VillageConfig:
    farmhands: int = 2
    starting_seed: int = 400
    starting_pantry: int = 5
    starting_owner_coin: int = 18
    starting_hand_coin: int = 3
    harvest_minutes: int = 95
    purchase_minutes: int = 8
    eat_minutes: int = 12
    rest_minutes: int = 110
    retry_minutes: int = 90
    harvest_min: int = 2
    harvest_max: int = 4
    wage: int = 2
    meal_price: int = 1
    meal_relief: int = 480
    fatigue_limit: int = 4
    work_fatigue: int = 2
    pantry_target: int = 10

    def __post_init__(self) -> None:
        integer("village.farmhands", self.farmhands, 1, 8)
        for name in ("starting_seed", "starting_pantry", "starting_owner_coin", "starting_hand_coin"):
            integer(f"village.{name}", getattr(self, name), 0, MAX_QUANTITY)
        for name in ("harvest_minutes", "purchase_minutes", "eat_minutes", "rest_minutes",
                     "retry_minutes", "meal_relief"):
            integer(f"village.{name}", getattr(self, name), 1, 100_000)
        for name in ("harvest_min", "wage", "meal_price", "fatigue_limit", "work_fatigue", "pantry_target"):
            integer(f"village.{name}", getattr(self, name), 1, MAX_QUANTITY)
        integer("village.harvest_max", self.harvest_max, self.harvest_min, MAX_QUANTITY)


@dataclass(frozen=True, slots=True)
class Config:
    """Tuning values frozen into each save, in simulated minutes and whole units."""

    minutes_per_day: int = 1440
    max_action_minutes: int = 1440
    max_events_per_advance: int = 50_000
    starting_grain_min: int = 8
    starting_grain_max: int = 16
    neighbor_starting_grain: int = 0
    village: VillageConfig = field(default_factory=VillageConfig)
    starting_standing_wood: int = DEFAULT_STANDING_WOOD
    starting_ore_deposit: int = DEFAULT_ORE_DEPOSIT

    def __post_init__(self) -> None:
        integer("minutes_per_day", self.minutes_per_day, 1, 100_000)
        integer("max_action_minutes", self.max_action_minutes, 1, 100_000)
        integer("max_events_per_advance", self.max_events_per_advance, 1, MAX_QUANTITY)
        integer("starting_grain_min", self.starting_grain_min, 2, MAX_QUANTITY)
        integer("starting_grain_max", self.starting_grain_max,
                self.starting_grain_min, MAX_QUANTITY)
        integer("neighbor_starting_grain", self.neighbor_starting_grain, 0, MAX_QUANTITY)
        integer("starting_standing_wood", self.starting_standing_wood, 0, MAX_QUANTITY)
        integer("starting_ore_deposit", self.starting_ore_deposit, 0, MAX_QUANTITY)
        if not isinstance(self.village, VillageConfig):
            raise WorldError("village settings must be a VillageConfig")

    @classmethod
    def from_mapping(cls, values: object) -> Self:
        options = config_fields(cls, values).copy()
        if "village" in options:
            options["village"] = VillageConfig(**config_fields(VillageConfig, options["village"]))
        return cls(**options)


@dataclass(frozen=True, slots=True)
class Actor:
    name: str
    location: str
    alive: bool = True
    hunger: int = 0
    fatigue: int = 0
    needs_updated_at: int = 0
    can_work: bool = True
    warm_until: int = 0


@dataclass(frozen=True, slots=True)
class Transfer:
    actor: str
    target: str
    quantity: int
    duration: int
    good: str = GRAIN


VillageActivity = Literal["harvest", "buy_food", "eat", "rest"]


@dataclass(frozen=True, slots=True)
class VillageIntent:
    kind: VillageActivity
    actor: str
    duration: int


@dataclass(frozen=True, slots=True)
class MarketIntent:
    kind: Literal["harvest", "buy_food", "eat"]
    actor: str
    duration: int
    farm: str
    price: int | None = None


@dataclass(frozen=True, slots=True)
class Travel:
    kind: ClassVar[Literal["travel"]] = "travel"
    actor: str
    source: str
    destination: str
    duration: int
    grain: int = 0


@dataclass(frozen=True, slots=True)
class FirewoodDelivery(Travel):
    firewood: int = 0


@dataclass(frozen=True, slots=True)
class OreDelivery(Travel):
    ore: int = 0


@dataclass(frozen=True, slots=True)
class FirewoodIntent:
    kind: Literal["cut_wood", "buy_firewood", "burn_firewood"]
    actor: str
    duration: int
    quantity: int = 1
    price: int | None = None


@dataclass(frozen=True, slots=True)
class CharcoalIntent:
    kind: Literal["make_charcoal"]
    actor: str
    duration: int


@dataclass(frozen=True, slots=True)
class MiningIntent:
    kind: Literal["mine_ore"]
    actor: str
    duration: int
    quantity: int


Intent = Transfer | VillageIntent | MarketIntent | Travel | FirewoodIntent | CharcoalIntent | MiningIntent


@dataclass(frozen=True, slots=True)
class Movement:
    source: str | None
    destination: str | None
    good: str
    quantity: int


@dataclass(slots=True)
class Action:
    intent: Intent
    started_at: int
    finishes_at: int
    start_event: int
    status: Literal["started", "completed", "failed", "canceled"] = "started"
    outcome_event: int | None = None


@dataclass(frozen=True, order=True, slots=True)
class Scheduled:
    minute: int
    priority: int
    sequence: int
    subject: str = field(compare=False)
    kind: Literal["complete", "decide"] = field(default="complete", compare=False)
    cause_id: int | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class Event:
    id: int
    minute: int
    kind: str
    payload: dict[str, object]
    cause_id: int | None = None


@dataclass(slots=True)
class World:
    seed: int
    config: Config
    rng_state: tuple[int, tuple[int, ...], float | None]
    actors: dict[str, Actor]
    inventory: dict[str, dict[str, int]]
    minute: int = 0
    next_sequence: int = 1
    next_event_id: int = 1
    actions: dict[str, Action] = field(default_factory=dict)
    queue: list[Scheduled] = field(default_factory=list)
    rules_version: int = RULES_VERSION
    content_version: str = LAB_CONTENT_VERSION

    def snapshot(self) -> dict[str, object]:
        data = asdict(self)
        data["queue"] = [asdict(event) for event in sorted(self.queue)]
        if self.content_version not in MARKET_CONTENT_VERSIONS:
            for actor in data["actors"].values():
                del actor["can_work"]
        if self.content_version not in FORESTRY_CONTENT_VERSIONS:
            if self.config.starting_standing_wood == DEFAULT_STANDING_WOOD:
                del data["config"]["starting_standing_wood"]
            for actor in data["actors"].values():
                del actor["warm_until"]
        if self.content_version != MINING_CONTENT_VERSION and self.config.starting_ore_deposit == DEFAULT_ORE_DEPOSIT:
            del data["config"]["starting_ore_deposit"]
        return data

    @classmethod
    def restore(cls, data: dict) -> Self:
        if (data["rules_version"] != RULES_VERSION
                or data["content_version"] not in (LAB_CONTENT_VERSION, *VILLAGE_CONTENT_VERSIONS)):
            raise WorldError("save uses unsupported rules or content")
        state_version, state_values, gaussian = data["rng_state"]
        actions: dict[str, Action] = {}
        for key, value in data["actions"].items():
            raw_intent = value["intent"]
            if "ore" in raw_intent:
                intent: Intent = OreDelivery(**raw_intent)
            elif "firewood" in raw_intent:
                intent = FirewoodDelivery(**raw_intent)
            elif "destination" in raw_intent:
                intent = Travel(**raw_intent)
            elif "farm" in raw_intent:
                intent = MarketIntent(**raw_intent)
            elif raw_intent.get("kind") in ("cut_wood", "buy_firewood", "burn_firewood"):
                intent = FirewoodIntent(**raw_intent)
            elif raw_intent.get("kind") == "make_charcoal":
                intent = CharcoalIntent(**raw_intent)
            elif raw_intent.get("kind") == "mine_ore":
                intent = MiningIntent(**raw_intent)
            elif "kind" in raw_intent:
                intent = VillageIntent(**raw_intent)
            else:
                intent = Transfer(**raw_intent)
            actions[key] = Action(**(value | {"intent": intent}))
        return cls(**(data | {
            "config": Config.from_mapping(data["config"]),
            "rng_state": (state_version, tuple(state_values), gaussian),
            "actors": {key: Actor(**value) for key, value in data["actors"].items()},
            "actions": actions,
            "queue": [Scheduled(**value) for value in data["queue"]],
        }))
