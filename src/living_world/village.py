"""Content and rules for the first autonomous food loop."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from random import Random

from . import routes
from .model import (
    COIN, FARM_OWNER, FARMSTEAD, FORESTRY_CONTENT_VERSIONS, GRAIN, MARKET_CONTENT_VERSIONS, MAX_CLOCK,
    SEED_GRAIN, SEED_SAVING_CONTENT_VERSIONS, SPATIAL_CONTENT_VERSIONS, VILLAGE_CONTENT_VERSION,
    VILLAGE_CONTENT_VERSIONS, Actor, CharcoalIntent, Config, FirewoodIntent, ForgeIntent, MarketIntent, MiningIntent, Movement,
    SmeltingIntent, ToolIntent, VillageActivity, VillageConfig, VillageIntent, World, WorldError,
)

FARMHAND_NAMES = ("Bren", "Oda", "Tavin", "Neri", "Merrit", "Sela", "Iven", "Linna")
NAME_ONSETS = ("Al", "Bel", "Cor", "Dun", "Eli", "Fen", "Gar", "Hal", "Ish", "Jor", "Kel", "Lor", "Mab", "Nol")
NAME_ENDINGS = ("a", "en", "ith", "or", "wyn", "ric", "elle", "an")


def farmhand_names(generation: Random, count: int) -> list[str]:
    """Sample the original catalog, then draw generated names only for larger villages."""
    names = generation.sample(FARMHAND_NAMES, min(count, len(FARMHAND_NAMES)))
    if count > len(FARMHAND_NAMES):
        extras = sorted(onset + ending for onset in NAME_ONSETS for ending in NAME_ENDINGS)
        names += generation.sample([name for name in extras if name not in names], count - len(names))
    return names


def create_village(seed: int, config: Config, generation: Random, farmhands: int | None = None) -> World:
    settings = config.village
    for duration in (settings.harvest_minutes, settings.purchase_minutes,
                     settings.eat_minutes, settings.rest_minutes):
        if duration > config.max_action_minutes:
            raise WorldError("village activity duration exceeds max_action_minutes")
    names = farmhand_names(generation, settings.farmhands if farmhands is None else farmhands)
    actors = {FARM_OWNER: Actor("Marra", FARMSTEAD)}
    actors.update({f"farmhand-{index}": Actor(name, FARMSTEAD) for index, name in enumerate(names, 1)})
    inventory = {actor: {GRAIN: 0, COIN: settings.starting_hand_coin} for actor in actors}
    inventory[FARM_OWNER] = {
        GRAIN: settings.starting_pantry,
        COIN: settings.starting_owner_coin,
        SEED_GRAIN: settings.starting_seed,
    }
    harvest = Random(f"living-world:harvest:{seed}")
    return World(seed, config, harvest.getstate(), actors, inventory,
                 content_version=VILLAGE_CONTENT_VERSION)


def duration(kind: VillageActivity, settings: VillageConfig) -> int:
    times = {
        "harvest": settings.harvest_minutes, "buy_food": settings.purchase_minutes,
        "eat": settings.eat_minutes, "rest": settings.rest_minutes,
    }
    if kind not in times:
        raise WorldError(f"unknown village activity {kind!r}")
    return times[kind]


def validate_activity(world: World, intent: VillageIntent | MarketIntent) -> None:
    if world.content_version not in VILLAGE_CONTENT_VERSIONS:
        raise WorldError("village activities require a village save")
    if intent.duration != duration(intent.kind, world.config.village):
        raise WorldError("duration does not match village activity rules")
    actor = world.actors[intent.actor]
    if world.content_version not in SPATIAL_CONTENT_VERSIONS and actor.location != FARMSTEAD:
        raise WorldError(f"{intent.kind} requires access to the farmstead")
    if world.content_version in MARKET_CONTENT_VERSIONS:
        if isinstance(intent, VillageIntent) and intent.kind in ("harvest", "buy_food"):
            raise WorldError("harvests and purchases in the market require a farm")
        return
    if intent.kind == "buy_food" and intent.actor == FARM_OWNER:
        raise WorldError("the farm owner already owns the pantry")
    if intent.kind in ("harvest", "buy_food") and intent.actor != FARM_OWNER:
        owner = world.actors[FARM_OWNER]
        if not owner.alive or owner.location != actor.location:
            raise WorldError("the farm owner is unavailable")


def activity_movements(
    intent: VillageIntent | MarketIntent, world: World, *, harvested: int = 0,
) -> tuple[Movement, ...]:
    actor = intent.actor
    farm = intent.farm if isinstance(intent, MarketIntent) else FARM_OWNER
    spatial = world.content_version in SPATIAL_CONTENT_VERSIONS
    pantry = routes.pantry(farm) if spatial else farm
    if intent.kind == "eat":
        source = pantry if isinstance(intent, MarketIntent) else actor
        return (Movement(source, None, GRAIN, 1),)
    if intent.kind == "buy_food":
        price = intent.price if isinstance(intent, MarketIntent) else world.config.village.meal_price
        assert price is not None
        return (
            Movement(routes.stall(farm) if spatial else farm, actor, GRAIN, 1),
            Movement(actor, farm, COIN, price),
        )
    if intent.kind == "harvest":
        movements = (Movement(pantry, None, SEED_GRAIN, 1),)
        if actor != farm:
            movements += (Movement(farm, actor, COIN, world.config.village.wage),)
        if harvested:
            saved_as_seed = 0
            if world.content_version in SEED_SAVING_CONTENT_VERSIONS:
                seed_after_planting = world.inventory[pantry][SEED_GRAIN] - 1
                reserve_gap = max(0, world.config.village.seed_reserve_target - seed_after_planting)
                saved_as_seed = min(reserve_gap, harvested // 2)
            movements += (Movement(None, pantry, GRAIN, harvested - saved_as_seed),)
            if saved_as_seed:
                movements += (Movement(None, pantry, SEED_GRAIN, saved_as_seed),)
        return movements
    return ()


def hunger_at(actor: Actor, minute: int, settings: VillageConfig) -> int:
    return min(settings.meal_relief * 3, actor.hunger + minute - actor.needs_updated_at)


def update_needs(
    world: World,
    intent: (
        VillageIntent | MarketIntent | FirewoodIntent | CharcoalIntent | MiningIntent
        | SmeltingIntent | ForgeIntent | ToolIntent
    ),
) -> dict[str, int | bool]:
    actor = world.actors[intent.actor]
    settings = world.config.village
    hunger = hunger_at(actor, world.minute, settings)
    fatigue = actor.fatigue
    warm_until = actor.warm_until
    details: dict[str, int | bool] = {}
    if intent.kind == "eat":
        hunger = max(0, hunger - settings.meal_relief)
    if intent.kind in ("harvest", "cut_wood", "make_charcoal", "mine_ore", "smelt_iron", "forge_hoe", "forge_hammer"):
        fatigue = min(settings.fatigue_limit, fatigue + settings.work_fatigue)
    if intent.kind == "rest":
        home = routes.fields_for(world).get(intent.actor)
        if world.content_version in FORESTRY_CONTENT_VERSIONS and home:
            heated = actor.location == home and warm_until > world.minute
            fatigue = 0 if heated else max(0, fatigue - settings.work_fatigue)
            details["heated"] = heated
        else:
            fatigue = 0
    if intent.kind == "burn_firewood":
        warm_until = min(MAX_CLOCK, world.minute + world.config.minutes_per_day)
        details["warm_until"] = warm_until
    world.actors[intent.actor] = replace(
        actor, hunger=hunger, fatigue=fatigue, needs_updated_at=world.minute, warm_until=warm_until,
    )
    return details | {"hunger": hunger, "fatigue": fatigue}


def choices(
    world: World, actor_id: str, personal_food: int, coin: int, pantry: int,
) -> Iterable[VillageActivity]:
    actor = world.actors[actor_id]
    settings = world.config.village
    if hunger_at(actor, world.minute, settings) >= settings.meal_relief:
        if personal_food:
            yield "eat"
        elif actor_id != FARM_OWNER:
            yield "buy_food"
    if actor.fatigue >= settings.fatigue_limit:
        yield "rest"
    elif actor_id == FARM_OWNER:
        if pantry < max(1, settings.pantry_target // 2):
            yield "harvest"
    elif coin < settings.meal_price * 2 or (
        coin < settings.meal_price * 3 and pantry < settings.pantry_target
    ):
        yield "harvest"
