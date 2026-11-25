"""Farm tool purchases, installation, and harvest wear."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from . import forestry, routes
from .model import (
    COIN, IRON_HOE, TOOLS_CONTENT_VERSION, TOOLS_CONTENT_VERSIONS, HoeHarvest, MarketIntent, Movement, ToolIntent,
    Travel, World, WorldError,
)
from .routes import BLACKSMITH, FARMS, MARKET_SQUARE

HOE_PRICE = 15
HOE_LIFETIME = 8
HOE_BONUS = 2
INSTALL_MINUTES = 10


def enable_tools(world: World) -> None:
    world.content_version = TOOLS_CONTENT_VERSION
    world.inventory[routes.stall(BLACKSMITH)] = {IRON_HOE: 0}
    world.hoe_uses = dict.fromkeys(FARMS, 0)
    for farm in FARMS:
        world.inventory[farm][IRON_HOE] = 0
        world.inventory[routes.pantry(farm)][IRON_HOE] = 0


def validate(world: World, intent: ToolIntent) -> None:
    fields = routes.fields_for(world)
    if world.content_version not in TOOLS_CONTENT_VERSIONS or intent.actor not in fields:
        raise WorldError("only farm owners can buy or install hoes in a tools save")
    actor = world.actors[intent.actor]
    if world.inventory[routes.pantry(intent.actor)][IRON_HOE]:
        raise WorldError("this farm already has an installed hoe")
    if intent.kind == "install_hoe":
        if actor.location != fields[intent.actor]:
            raise WorldError("a hoe must be installed at the buyer's farm")
        if intent.duration != INSTALL_MINUTES or intent.price is not None:
            raise WorldError("installing a hoe requires the installation duration")
        return

    if intent.kind != "buy_hoe":
        raise WorldError(f"unknown tool activity {intent.kind!r}")
    if actor.location != MARKET_SQUARE or not world.actors[BLACKSMITH].alive:
        raise WorldError("buying a hoe requires a customer at the open blacksmith stall")
    if world.inventory[intent.actor][IRON_HOE]:
        raise WorldError("this farmer already carries a hoe")
    if type(intent.price) is not int or intent.price != HOE_PRICE:
        raise WorldError(f"a hoe costs {HOE_PRICE} coins")
    if intent.duration != world.config.village.purchase_minutes:
        raise WorldError("duration does not match the hoe purchase rules")


def movements(intent: ToolIntent) -> tuple[Movement, ...]:
    if intent.kind == "install_hoe":
        return (Movement(intent.actor, routes.pantry(intent.actor), IRON_HOE, 1),)
    return (
        Movement(routes.stall(BLACKSMITH), intent.actor, IRON_HOE, 1),
        Movement(intent.actor, BLACKSMITH, COIN, HOE_PRICE),
    )


def usable(world: World, farm: str) -> bool:
    return (world.hoe_uses.get(farm, 0) > 0
            and world.inventory[routes.pantry(farm)].get(IRON_HOE, 0) > 0)


def validate_harvest(world: World, intent: HoeHarvest) -> None:
    if (world.content_version not in TOOLS_CONTENT_VERSIONS
            or intent.kind != "harvest" or intent.with_hoe is not True):
        raise WorldError("using a hoe requires a harvest in a tools save")
    if not usable(world, intent.farm):
        raise WorldError(f"there is no usable hoe at {intent.farm}")


def harvest(
    world: World, actor: str, duration: int, farm: str, hoe_is_free: Callable[[str], bool],
) -> MarketIntent:
    if usable(world, farm) and hoe_is_free(farm):
        return HoeHarvest("harvest", actor, duration, farm)
    return MarketIntent("harvest", actor, duration, farm)


def wear(world: World, farm: str) -> tuple[Movement, ...]:
    world.hoe_uses[farm] -= 1
    if world.hoe_uses[farm] == 0:
        return (Movement(routes.pantry(farm), None, IRON_HOE, 1),)
    return ()


def procurement(
    world: World, farm: str, available: forestry.Available, delivery_grain: int,
) -> Iterator[ToolIntent | Travel]:
    actor = world.actors[farm]
    if usable(world, farm):
        return
    home = routes.fields_for(world)[farm]
    if available(farm, IRON_HOE):
        if actor.location == home:
            yield ToolIntent("install_hoe", farm, INSTALL_MINUTES)
        else:
            yield routes.next_leg(world, farm, actor.location, home)
    elif (available(farm, COIN) >= HOE_PRICE + world.config.village.meal_price
          and world.actors[BLACKSMITH].alive and available(routes.stall(BLACKSMITH), IRON_HOE)):
        if actor.location == MARKET_SQUARE:
            yield ToolIntent("buy_hoe", farm, world.config.village.purchase_minutes, price=HOE_PRICE)
        else:
            grain = delivery_grain if actor.location == home else 0
            yield routes.next_leg(world, farm, actor.location, MARKET_SQUARE, grain=grain)
