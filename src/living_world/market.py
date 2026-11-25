"""Two grain farms and standing offers backed by their pantry stocks."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from random import Random
from typing import Literal

from . import blacksmith, contracts, farm_tools, forestry, kiln, mining, routes, seed_trade, smelting, village
from .model import (
    BLACKSMITH_CONTENT_VERSIONS, COIN, CONTRACTS_CONTENT_VERSIONS, FARM_OWNER, FARMSTEAD, FIREWOOD,
    FORESTRY_CONTENT_VERSIONS, GRAIN,
    HAMLET_CONTENT_VERSIONS, MARKET_CONTENT_VERSION, MARKET_CONTENT_VERSIONS,
    SEED_GRAIN, SEED_TRADE_CONTENT_VERSIONS, SMELTING_CONTENT_VERSIONS, STANDING_WOOD,
    SPATIAL_CONTENT_VERSIONS, TOOLS_CONTENT_VERSIONS, WORKSHOP_CONTENT_VERSIONS,
    Actor, Config, ForgeIntent, Intent, MarketIntent,
    VillageIntent, World, WorldError,
)
from .routes import FARMS, WEST_FARM

FOOD_RESERVE = 2
SHOCKS = ("seed-shortage", "worker-loss")
MarketShock = Literal["seed-shortage", "worker-loss"]
Available = Callable[[str, str], int]


@dataclass(frozen=True, slots=True)
class GrainOffer:
    seller: str
    quantity: int
    price: int


def create_market(seed: int, config: Config, generation: Random, farmhands: int | None = None) -> World:
    world = village.create_village(seed, config, generation, farmhands)
    world.content_version = MARKET_CONTENT_VERSION
    world.actors[WEST_FARM] = Actor("Tessa", FARMSTEAD)
    world.inventory[WEST_FARM] = world.inventory[FARM_OWNER].copy()
    return world


def offers(world: World, available: Available) -> list[GrainOffer]:
    settings = world.config.village
    stocked_threshold = max(2, settings.pantry_target // 3)
    result: list[GrainOffer] = []
    for seller in routes.fields_for(world):
        actor = world.actors[seller]
        if not actor.alive:
            continue
        if world.content_version in SPATIAL_CONTENT_VERSIONS:
            quantity = available(routes.stall(seller), GRAIN)
        else:
            if actor.location != FARMSTEAD:
                continue
            quantity = available(seller, GRAIN) - FOOD_RESERVE
        if quantity > 0:
            price = settings.meal_price if quantity >= stocked_threshold else settings.meal_price * 2
            result.append(GrainOffer(seller, quantity, price))
    return sorted(result, key=lambda offer: (offer.price, -offer.quantity, offer.seller))


def validate_activity(world: World, intent: MarketIntent) -> None:
    if world.content_version not in MARKET_CONTENT_VERSIONS:
        raise WorldError("farm-specific activities require a market save")
    fields = routes.fields_for(world)
    if intent.farm not in fields:
        raise WorldError(f"unknown farm {intent.farm!r}")
    farm = world.actors[intent.farm]
    actor = world.actors[intent.actor]
    if not farm.alive:
        raise WorldError(f"farm {intent.farm!r} is unavailable")
    if world.content_version in SPATIAL_CONTENT_VERSIONS:
        site = routes.MARKET_SQUARE if intent.kind == "buy_food" else fields[intent.farm]
        if site != actor.location:
            raise WorldError(f"{intent.kind} requires being at {site}")
    elif farm.location != actor.location:
        raise WorldError(f"farm {intent.farm!r} is unavailable")
    if intent.kind == "buy_food":
        if intent.actor == intent.farm:
            raise WorldError("buyers must choose another seller")
        if type(intent.price) is not int or intent.price <= 0:
            raise WorldError("purchase requires a positive integer quote")
    elif intent.kind == "harvest":
        if intent.price is not None:
            raise WorldError("a harvest cannot specify a purchase price")
        if not world.actors[intent.actor].can_work:
            raise WorldError(f"actor {intent.actor!r} is unavailable for field work")
        if intent.actor in fields and intent.actor != intent.farm:
            raise WorldError("farm owners work their own fields")
    elif (world.content_version not in SPATIAL_CONTENT_VERSIONS or intent.actor != intent.farm
          or intent.price is not None):
        raise WorldError("only the owner can eat directly from their field pantry")


def choices(
    world: World, actor_id: str, available: Available,
) -> Iterator[VillageIntent | MarketIntent]:
    actor = world.actors[actor_id]
    settings = world.config.village
    personal_food = available(actor_id, GRAIN)
    if village.hunger_at(actor, world.minute, settings) >= settings.meal_relief:
        if personal_food:
            yield VillageIntent("eat", actor_id, settings.eat_minutes)
        else:
            for offer in offers(world, available):
                if offer.seller != actor_id:
                    yield MarketIntent("buy_food", actor_id, settings.purchase_minutes,
                                       offer.seller, offer.price)
    if actor.fatigue >= settings.fatigue_limit:
        yield VillageIntent("rest", actor_id, settings.rest_minutes)
        return
    if not actor.can_work:
        return
    if actor_id in FARMS:
        if personal_food < max(FOOD_RESERVE + 1, settings.pantry_target // 2 + FOOD_RESERVE):
            yield MarketIntent("harvest", actor_id, settings.harvest_minutes, actor_id)
        return

    coin = available(actor_id, COIN)
    if coin < settings.meal_price * 4:
        for farm in sorted(FARMS, key=lambda owner: (available(owner, GRAIN), owner)):
            if coin < settings.meal_price * 3 or available(farm, GRAIN) < settings.pantry_target:
                yield MarketIntent("harvest", actor_id, settings.harvest_minutes, farm)


def woodcutter_out_of_work(world: World, available: Available) -> bool:
    """In the hamlet, a woodcutter seeks field shifts when there is nothing left to cut,
    or when cash is low and stock already at the stall is not selling."""
    if world.content_version not in HAMLET_CONTENT_VERSIONS:
        return False
    exhausted = (not available(forestry.WOODLAND_STOCK, STANDING_WOOD)
                 and not available(routes.WOODPILE, FIREWOOD))
    unsold = (available(routes.stall(routes.WOODCUTTER), FIREWOOD) > 0
              and available(routes.WOODCUTTER, COIN) < world.config.village.meal_price * 4)
    return exhausted or unsold


def route_choices(
    world: World, actor_id: str, available: Available, shift_open: Callable[[str], bool],
    hoe_is_free: Callable[[str], bool], *, forge_open: bool = True, forge_hire_inbound: bool = False,
) -> Iterator[Intent]:
    actor = world.actors[actor_id]
    settings = world.config.village
    site = actor.location
    fields = routes.fields_for(world)
    home = fields.get(actor_id)
    coin = available(actor_id, COIN)
    pantry_stock = available(routes.pantry(actor_id), GRAIN) if home else 0
    target = max(3, settings.pantry_target // 2)
    delivery_grain = (
        max(0, min(pantry_stock - FOOD_RESERVE, target - available(routes.stall(actor_id), GRAIN)))
        if home else 0
    )
    if village.hunger_at(actor, world.minute, settings) >= settings.meal_relief:
        if available(actor_id, GRAIN):
            yield VillageIntent("eat", actor_id, settings.eat_minutes)
        elif home and site == home and pantry_stock:
            yield MarketIntent("eat", actor_id, settings.eat_minutes, actor_id)
        elif home and site != home and pantry_stock:
            yield routes.next_leg(world, actor_id, site, home)
        elif site == routes.MARKET_SQUARE:
            for offer in offers(world, available):
                if offer.seller != actor_id:
                    yield MarketIntent("buy_food", actor_id, settings.purchase_minutes,
                                       offer.seller, offer.price)
        elif coin >= settings.meal_price:
            if actor_id == routes.WOODCUTTER and site == routes.WOODLAND:
                yield forestry.to_market(world, available)
            elif actor_id == routes.MINER and site == routes.MINE:
                yield mining.to_market(world, available)
            elif (world.content_version in SMELTING_CONTENT_VERSIONS
                  and actor_id == routes.CHARCOAL_BURNER and site == routes.KILN):
                yield kiln.to_market(world, available)
            elif (world.content_version in BLACKSMITH_CONTENT_VERSIONS
                  and actor_id == routes.SMELTER and site == routes.SMELTERY):
                yield smelting.to_market(world, available)
            elif (world.content_version in TOOLS_CONTENT_VERSIONS
                  and actor_id == routes.BLACKSMITH and site == routes.FORGE):
                yield blacksmith.to_market(world, available)
            else:
                yield routes.next_leg(world, actor_id, site, routes.MARKET_SQUARE)

    if world.content_version in FORESTRY_CONTENT_VERSIONS:
        yield from forestry.hearth(world, actor_id, available, delivery_grain)
    if actor.fatigue >= settings.fatigue_limit:
        yield VillageIntent("rest", actor_id, settings.rest_minutes)
        return
    if world.content_version in SEED_TRADE_CONTENT_VERSIONS and home:
        yield from seed_trade.procurement(world, actor_id, available)
    if world.content_version in CONTRACTS_CONTENT_VERSIONS and home:
        yield from contracts.farm_choices(world, actor_id, available)
    if (world.content_version in TOOLS_CONTENT_VERSIONS and home
            and (world.content_version not in CONTRACTS_CONTENT_VERSIONS or not contracts.has_order(world, actor_id))):
        yield from farm_tools.procurement(world, actor_id, available, delivery_grain)
    if actor_id == routes.CHARCOAL_BURNER:
        yield from kiln.work(world, available)
    elif actor_id == routes.MINER:
        yield from mining.work(world, available)
    elif actor_id == routes.SMELTER:
        yield from smelting.work(world, available)
    elif actor_id == routes.BLACKSMITH:
        if world.content_version in CONTRACTS_CONTENT_VERSIONS:
            yield from contracts.smith_choices(world, available)
        yield from blacksmith.work(world, available, hire_inbound=forge_hire_inbound)
    if actor_id == routes.WOODCUTTER and not woodcutter_out_of_work(world, available):
        yield from forestry.work(world, available)
    elif home:
        if site != home:
            # A farmer shopping for food stays at the square to wait for stock,
            # unless there is food at home or enough seed to resume work there.
            if pantry_stock or available(routes.pantry(actor_id), SEED_GRAIN):
                yield routes.next_leg(world, actor_id, site, home)
        elif delivery_grain > 0:
            yield routes.next_leg(world, actor_id, site, routes.MARKET_SQUARE, grain=delivery_grain)
        elif pantry_stock < settings.pantry_target:
            yield farm_tools.harvest(world, actor_id, settings.harvest_minutes, actor_id, hoe_is_free)
    elif actor.can_work and coin < settings.meal_price * 4:
        if (world.content_version in WORKSHOP_CONTENT_VERSIONS and actor_id.startswith("farmhand-")
                and forge_open and not forge_hire_inbound and blacksmith.can_hire(world, available)):
            if site == routes.FORGE:
                yield ForgeIntent("forge_hoe", actor_id, blacksmith.FORGE_MINUTES)
            elif site == routes.MARKET_SQUARE:
                yield routes.next_leg(world, actor_id, site, routes.FORGE)
        for farm in sorted(fields, key=lambda owner: (routes.distance(world, site, fields[owner]), owner)):
            pantry = routes.pantry(farm)
            field = fields[farm]
            if (not world.actors[farm].alive or not shift_open(farm)
                    or available(pantry, SEED_GRAIN) == 0 or available(farm, COIN) < settings.wage):
                continue
            if coin < settings.meal_price * 3 or available(pantry, GRAIN) < settings.pantry_target:
                if site == field:
                    yield farm_tools.harvest(world, actor_id, settings.harvest_minutes, farm, hoe_is_free)
                else:
                    yield routes.next_leg(world, actor_id, site, field)
