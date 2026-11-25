"""Market purchases of iron and timed production of farm tools."""

from __future__ import annotations

from collections.abc import Iterator

from . import forestry, routes
from .model import (
    ANVIL, APPRENTICESHIP_CONTENT_VERSION, BLACKSMITH_CONTENT_VERSION, BLACKSMITH_CONTENT_VERSIONS,
    CIVILIAN_CONTENT_VERSIONS, COIN, FIREWOOD, GRAIN, IRON, IRON_HAMMER, IRON_HOE,
    TOOLS_CONTENT_VERSIONS, WORKSHOP_CONTENT_VERSIONS,
    Actor, FirewoodIntent, ForgeIntent, HoeDelivery, Movement, PersonalForge, Travel, World, WorldError,
)
from .routes import BLACKSMITH, FORGE, MARKET_SQUARE, SMELTER, TOOL_STOCK

IRON_PRICE = 12
FORGE_MINUTES = 140
HOE_TARGET = 3
STARTING_COIN = 42
FORGE_INPUTS = "forge-inputs"
EXPERIENCED_XP = 9
FORGE_RENT = 1
HOE_BUYBACK = 16
HAMMER_LESSON_MINUTES = 60
HAMMER_LESSON_PRICE = 2
FORGE_RECIPES = {"forge_hoe": (IRON_HOE, FORGE_MINUTES), "forge_hammer": (IRON_HAMMER, 160)}
WORKSHOP_ACTIVITIES = (*FORGE_RECIPES, "learn_hammer")


def skill_rank(xp: int) -> int:
    return min(5, xp // 3)


def accepts_tools(world: World, available: forestry.Available) -> bool:
    return (world.actors[BLACKSMITH].alive
            and available(routes.stall(BLACKSMITH), IRON_HOE) + available(TOOL_STOCK, IRON_HOE) < HOE_TARGET)


def can_hire(world: World, available: forestry.Available) -> bool:
    settings = world.config.village
    return (
        world.actors[BLACKSMITH].alive
        and available(routes.stall(BLACKSMITH), IRON_HOE) < HOE_TARGET
        and available(FORGE_INPUTS, IRON) > 0
        and available(BLACKSMITH, COIN) >= settings.wage + settings.meal_price * 2
        and (world.content_version not in CIVILIAN_CONTENT_VERSIONS
             or (available(FORGE_INPUTS, FIREWOOD) > 0 and available(FORGE_INPUTS, ANVIL) > 0))
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
    if isinstance(intent, PersonalForge) and (
        world.content_version not in CIVILIAN_CONTENT_VERSIONS or intent.kind not in FORGE_RECIPES
        or intent.actor == BLACKSMITH or intent.personal is not True
    ):
        raise WorldError("renting the forge requires a civilian worker with their own materials")
    if intent.kind == "learn_hammer":
        if world.content_version != APPRENTICESHIP_CONTENT_VERSION or intent.actor == BLACKSMITH:
            raise WorldError("hammer lessons require a student in the apprenticeship scenario")
        if intent.actor in world.hammer_training:
            raise WorldError("you already know the hammer recipe")
        mentor = world.actors[BLACKSMITH]
        if actor.location != FORGE or mentor.location != FORGE or not mentor.alive or not mentor.can_work:
            raise WorldError("hammer lessons require Ada and the student at the forge")
        if intent.duration != HAMMER_LESSON_MINUTES or intent.price is not None:
            raise WorldError("a hammer lesson takes 60 simulated minutes")
        return
    if intent.kind == "sell_hoe":
        if (world.content_version not in CIVILIAN_CONTENT_VERSIONS or intent.actor == BLACKSMITH
                or actor.location != MARKET_SQUARE or not world.actors[BLACKSMITH].alive):
            raise WorldError("selling a hoe requires Ada's stall at the market square")
        if type(intent.price) is not int or intent.price != HOE_BUYBACK:
            raise WorldError(f"Ada pays {HOE_BUYBACK} coins per hoe")
        if intent.duration != world.config.village.purchase_minutes:
            raise WorldError("duration does not match the hoe trade")
        return
    if intent.kind in ("store_forge_iron", "store_forge_fuel"):
        if (world.content_version not in WORKSHOP_CONTENT_VERSIONS or intent.actor != BLACKSMITH
                or actor.location != FORGE or intent.duration != 1 or intent.price is not None):
            raise WorldError("only the blacksmith can unload supplies at the hamlet forge")
        if intent.kind == "store_forge_fuel" and world.content_version not in CIVILIAN_CONTENT_VERSIONS:
            raise WorldError("unloading fuel requires a civilian forge")
        return
    if intent.kind in FORGE_RECIPES:
        tool = intent.kind.removeprefix("forge_")
        if intent.kind == "forge_hammer":
            if world.content_version != APPRENTICESHIP_CONTENT_VERSION or not isinstance(intent, PersonalForge):
                raise WorldError("hammer making requires renting the forge in the apprenticeship scenario")
            if intent.actor not in world.hammer_training:
                raise WorldError("learn the hammer recipe from Ada first")
        hired = (world.content_version in WORKSHOP_CONTENT_VERSIONS and world.actors[BLACKSMITH].alive
                 and (intent.actor.startswith("farmhand-")
                      or (world.content_version in CIVILIAN_CONTENT_VERSIONS and intent.actor == world.player_id)))
        if (intent.actor != BLACKSMITH and not hired) or actor.location != FORGE or not actor.can_work:
            if world.content_version not in WORKSHOP_CONTENT_VERSIONS:
                raise WorldError("only the blacksmith can make a hoe at the forge")
            raise WorldError(f"making a {tool} requires an eligible worker at the forge")
        if intent.duration != FORGE_RECIPES[intent.kind][1] or intent.price is not None:
            raise WorldError(f"making a {tool} requires the forging duration")
        if world.content_version in CIVILIAN_CONTENT_VERSIONS and not world.inventory[FORGE_INPUTS][ANVIL]:
            raise WorldError(f"making a {tool} requires an anvil at the forge")
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
    if intent.kind == "learn_hammer":
        return (Movement(intent.actor, BLACKSMITH, COIN, HAMMER_LESSON_PRICE),)
    if intent.kind == "store_forge_iron":
        return (Movement(BLACKSMITH, FORGE_INPUTS, IRON, 1),)
    if intent.kind == "store_forge_fuel":
        return (Movement(BLACKSMITH, FORGE_INPUTS, FIREWOOD, 1),)
    if intent.kind == "sell_hoe":
        return (
            Movement(intent.actor, routes.stall(BLACKSMITH), IRON_HOE, 1),
            Movement(BLACKSMITH, intent.actor, COIN, HOE_BUYBACK),
        )
    if intent.kind in FORGE_RECIPES:
        product, _ = FORGE_RECIPES[intent.kind]
        if isinstance(intent, PersonalForge):
            return (
                Movement(intent.actor, None, IRON, 1),
                Movement(intent.actor, None, FIREWOOD, 1),
                Movement(intent.actor, BLACKSMITH, COIN, FORGE_RENT),
                Movement(None, intent.actor, product, 1),
            )
        source = FORGE_INPUTS if world.content_version in WORKSHOP_CONTENT_VERSIONS else intent.actor
        output = (Movement(source, None, IRON, 1),)
        if world.content_version in CIVILIAN_CONTENT_VERSIONS:
            output += (Movement(FORGE_INPUTS, None, FIREWOOD, 1),)
        output += (Movement(None, TOOL_STOCK, IRON_HOE, 1),)
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
         ) -> Iterator[FirewoodIntent | ForgeIntent | Travel]:
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
    if world.content_version in CIVILIAN_CONTENT_VERSIONS and not available(FORGE_INPUTS, FIREWOOD):
        if available(BLACKSMITH, FIREWOOD):
            if actor.location == FORGE:
                yield ForgeIntent("store_forge_fuel", BLACKSMITH, 1)
            else:
                yield routes.next_leg(world, BLACKSMITH, actor.location, FORGE)
        elif (available(BLACKSMITH, COIN) >= forestry.FIREWOOD_PRICE
              and world.actors[routes.WOODCUTTER].alive
              and available(routes.stall(routes.WOODCUTTER), FIREWOOD)):
            if actor.location == MARKET_SQUARE:
                yield FirewoodIntent("buy_firewood", BLACKSMITH, world.config.village.purchase_minutes,
                                     price=forestry.FIREWOOD_PRICE)
            else:
                yield routes.next_leg(world, BLACKSMITH, actor.location, MARKET_SQUARE)
        return
    if world.content_version in WORKSHOP_CONTENT_VERSIONS:
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
