"""Market purchases of iron and timed production of farm tools."""

from __future__ import annotations

from collections.abc import Iterator

from . import forestry, routes
from .model import (
    BLACKSMITH_CONTENT_VERSION, BLACKSMITH_CONTENT_VERSIONS, COIN, GRAIN, HAMLET_CONTENT_VERSION,
    IRON, IRON_HOE, TOOLS_CONTENT_VERSIONS, Actor, ForgeIntent, HoeDelivery, Movement, Travel,
    World, WorldError,
)
from .routes import BLACKSMITH, FORGE, MARKET_SQUARE, SMELTER, TOOL_STOCK

IRON_PRICE = 12
FORGE_MINUTES = 140
HOE_TARGET = 3
STARTING_COIN = 42
FORGE_INPUTS = "forge-inputs"


def can_hire(world: World, available: forestry.Available) -> bool:
    settings = world.config.village
    return (
        world.actors[BLACKSMITH].alive
        and available(routes.stall(BLACKSMITH), IRON_HOE) < HOE_TARGET
        and available(FORGE_INPUTS, IRON) > 0
        and available(BLACKSMITH, COIN) >= settings.wage + settings.meal_price * 2
    )


def add_forge(world: World) -> None:
    world.content_version = BLACKSMITH_CONTENT_VERSION
    world.actors[BLACKSMITH] = Actor("Ada", FORGE)
    world.inventory[BLACKSMITH] = {COIN: STARTING_COIN, GRAIN: 0, IRON: 0}
    world.inventory[routes.stall(SMELTER)] = {IRON: 0}
    world.inventory[TOOL_STOCK] = {IRON_HOE: 0}


def validate(world: World, intent: ForgeIntent) -> None:
    if world.content_version not in BLACKSMITH_CONTENT_VERSIONS:
        raise WorldError("iron purchases and forging require a save with a blacksmith")
    actor = world.actors[intent.actor]
    if intent.kind == "store_forge_iron":
        if (world.content_version != HAMLET_CONTENT_VERSION or intent.actor != BLACKSMITH
                or actor.location != FORGE or intent.duration != 1 or intent.price is not None):
            raise WorldError("only the blacksmith can unload iron at the hamlet forge")
        return
    if intent.kind == "forge_hoe":
        hired = (world.content_version == HAMLET_CONTENT_VERSION
                 and intent.actor.startswith("farmhand-") and world.actors[BLACKSMITH].alive)
        if (intent.actor != BLACKSMITH and not hired) or actor.location != FORGE or not actor.can_work:
            if world.content_version != HAMLET_CONTENT_VERSION:
                raise WorldError("only the blacksmith can make a hoe at the forge")
            raise WorldError("making a hoe requires an eligible worker at the forge")
        if intent.duration != FORGE_MINUTES or intent.price is not None:
            raise WorldError("making a hoe requires the forging duration")
        return

    if intent.kind != "buy_iron":
        raise WorldError(f"unknown forge activity {intent.kind!r}")
    if actor.location != MARKET_SQUARE or intent.actor == SMELTER:
        raise WorldError("buying iron requires a customer at the market square")
    if not world.actors[SMELTER].alive:
        raise WorldError("the smelter's stall is closed")
    if type(intent.price) is not int or intent.price != IRON_PRICE:
        raise WorldError(f"iron costs {IRON_PRICE} coins per unit")
    if intent.duration != world.config.village.purchase_minutes:
        raise WorldError("duration does not match the iron purchase rules")


def movements(world: World, intent: ForgeIntent) -> tuple[Movement, ...]:
    if intent.kind == "store_forge_iron":
        return (Movement(BLACKSMITH, FORGE_INPUTS, IRON, 1),)
    if intent.kind == "forge_hoe":
        source = FORGE_INPUTS if world.content_version == HAMLET_CONTENT_VERSION else intent.actor
        output = (
            Movement(source, None, IRON, 1),
            Movement(None, TOOL_STOCK, IRON_HOE, 1),
        )
        if intent.actor != BLACKSMITH:
            output += (Movement(BLACKSMITH, intent.actor, COIN, world.config.village.wage),)
        return output
    return (
        Movement(routes.stall(SMELTER), intent.actor, IRON, 1),
        Movement(intent.actor, SMELTER, COIN, IRON_PRICE),
    )


def to_market(world: World, available: forestry.Available) -> Travel:
    duration = routes.distance(world, FORGE, MARKET_SQUARE)
    quantity = min(available(TOOL_STOCK, IRON_HOE),
                   HOE_TARGET - available(routes.stall(BLACKSMITH), IRON_HOE))
    if quantity > 0:
        return HoeDelivery(BLACKSMITH, FORGE, MARKET_SQUARE, duration, hoes=quantity)
    return Travel(BLACKSMITH, FORGE, MARKET_SQUARE, duration)


def work(world: World, available: forestry.Available, *, hire_inbound: bool = False
         ) -> Iterator[ForgeIntent | Travel]:
    actor = world.actors[BLACKSMITH]
    if not actor.can_work:
        return
    local_stock = available(TOOL_STOCK, IRON_HOE)
    if world.content_version in TOOLS_CONTENT_VERSIONS:
        if available(routes.stall(BLACKSMITH), IRON_HOE) >= HOE_TARGET:
            return
        if local_stock:
            if actor.location == FORGE:
                yield to_market(world, available)
            else:
                yield routes.next_leg(world, BLACKSMITH, actor.location, FORGE)
            return
    elif local_stock >= HOE_TARGET:
        return
    if world.content_version == HAMLET_CONTENT_VERSION:
        if available(FORGE_INPUTS, IRON):
            if hire_inbound and can_hire(world, available):
                return
            if actor.location == FORGE:
                yield ForgeIntent("forge_hoe", BLACKSMITH, FORGE_MINUTES)
            else:
                yield routes.next_leg(world, BLACKSMITH, actor.location, FORGE)
            return
        if available(BLACKSMITH, IRON):
            if actor.location == FORGE:
                yield ForgeIntent("store_forge_iron", BLACKSMITH, 1)
            else:
                yield routes.next_leg(world, BLACKSMITH, actor.location, FORGE)
            return
    elif available(BLACKSMITH, IRON):
        if actor.location == FORGE:
            yield ForgeIntent("forge_hoe", BLACKSMITH, FORGE_MINUTES)
        else:
            yield routes.next_leg(world, BLACKSMITH, actor.location, FORGE)
        return
    if (available(BLACKSMITH, COIN) >= IRON_PRICE and world.actors[SMELTER].alive
          and available(routes.stall(SMELTER), IRON)):
        if actor.location == MARKET_SQUARE:
            yield ForgeIntent("buy_iron", BLACKSMITH, world.config.village.purchase_minutes,
                              price=IRON_PRICE)
        else:
            yield routes.next_leg(world, BLACKSMITH, actor.location, MARKET_SQUARE)
