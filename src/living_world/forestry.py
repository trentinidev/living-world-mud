"""Finite woodland extraction, market fuel, and farm hearths."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from . import routes
from .model import (
    COIN, FIREWOOD, FIREWOOD_CONTENT_VERSION, FORESTRY_CONTENT_VERSIONS, GRAIN, STANDING_WOOD,
    Actor, FirewoodDelivery, FirewoodIntent, Movement, Travel, World, WorldError, integer,
)
from .routes import WOODCUTTER, WOODLAND, WOODPILE

WOODLAND_STOCK = "woodland-stock"
FIREWOOD_PRICE = 2
CUT_MINUTES = 70
CUT_LIMIT = 3
HEARTH_MINUTES = 10
STALL_TARGET = 4
Available = Callable[[str, str], int]


def add_woodland(world: World) -> None:
    if CUT_MINUTES > world.config.max_action_minutes:
        raise WorldError("cutting wood takes longer than max_action_minutes")
    world.content_version = FIREWOOD_CONTENT_VERSION
    world.actors[WOODCUTTER] = Actor("Rowan", WOODLAND)
    world.inventory[WOODCUTTER] = {COIN: 6, GRAIN: 0}
    world.inventory[WOODLAND_STOCK] = {STANDING_WOOD: world.config.starting_standing_wood}
    world.inventory[WOODPILE] = {FIREWOOD: 0}
    world.inventory[routes.stall(WOODCUTTER)] = {FIREWOOD: 0}


def validate(world: World, intent: FirewoodIntent) -> None:
    if world.content_version not in FORESTRY_CONTENT_VERSIONS:
        raise WorldError("firewood activities require a save with a woodland")
    actor = world.actors[intent.actor]
    if intent.kind == "cut_wood":
        if intent.actor != WOODCUTTER or actor.location != WOODLAND or not actor.can_work:
            raise WorldError("only the woodcutter can cut wood at the woodland")
        integer("cut quantity", intent.quantity, 1, CUT_LIMIT)
        if intent.duration != CUT_MINUTES or intent.price is not None:
            raise WorldError("cutting wood requires the woodland work duration")
    elif intent.kind == "buy_firewood":
        if actor.location != routes.MARKET_SQUARE or intent.actor == WOODCUTTER:
            raise WorldError("buying firewood requires a customer at the market square")
        if not world.actors[WOODCUTTER].alive:
            raise WorldError("the firewood stall is closed")
        integer("purchase quantity", intent.quantity, 1, 1)
        if type(intent.price) is not int or intent.price != FIREWOOD_PRICE:
            raise WorldError(f"firewood costs {FIREWOOD_PRICE} coins per bundle")
        if intent.duration != world.config.village.purchase_minutes:
            raise WorldError("duration does not match the firewood purchase rules")
    elif intent.kind == "burn_firewood":
        if actor.location != routes.FIELDS.get(intent.actor):
            raise WorldError("heating requires the farm owner to be at their own hearth")
        if actor.warm_until > world.minute:
            raise WorldError("the hearth is still warm")
        integer("burn quantity", intent.quantity, 1, 1)
        if intent.duration != HEARTH_MINUTES or intent.price is not None:
            raise WorldError("heating requires the hearth activity duration")
    else:
        raise WorldError(f"unknown firewood activity {intent.kind!r}")


def movements(intent: FirewoodIntent) -> tuple[Movement, ...]:
    if intent.kind == "cut_wood":
        return (
            Movement(WOODLAND_STOCK, None, STANDING_WOOD, intent.quantity),
            Movement(None, WOODPILE, FIREWOOD, intent.quantity),
        )
    if intent.kind == "buy_firewood":
        return (
            Movement(routes.stall(WOODCUTTER), intent.actor, FIREWOOD, intent.quantity),
            Movement(intent.actor, WOODCUTTER, COIN, FIREWOOD_PRICE),
        )
    return (Movement(intent.actor, None, FIREWOOD, intent.quantity),)


def to_market(world: World, available: Available) -> Travel:
    duration = routes.distance(world, WOODLAND, routes.MARKET_SQUARE)
    quantity = min(available(WOODPILE, FIREWOOD),
                   STALL_TARGET - available(routes.stall(WOODCUTTER), FIREWOOD))
    if quantity > 0:
        return FirewoodDelivery(WOODCUTTER, WOODLAND, routes.MARKET_SQUARE, duration, firewood=quantity)
    return Travel(WOODCUTTER, WOODLAND, routes.MARKET_SQUARE, duration)


def work(world: World, available: Available) -> Iterator[FirewoodIntent | Travel]:
    if not world.actors[WOODCUTTER].can_work:
        return
    if available(routes.stall(WOODCUTTER), FIREWOOD) >= STALL_TARGET:
        return
    site = world.actors[WOODCUTTER].location
    standing = available(WOODLAND_STOCK, STANDING_WOOD)
    if site == WOODLAND:
        if available(WOODPILE, FIREWOOD):
            yield to_market(world, available)
        elif standing:
            yield FirewoodIntent("cut_wood", WOODCUTTER, CUT_MINUTES, min(CUT_LIMIT, standing))
    elif standing or available(WOODPILE, FIREWOOD):
        yield routes.next_leg(world, WOODCUTTER, site, WOODLAND)


def hearth(
    world: World, actor_id: str, available: Available, delivery_grain: int,
) -> Iterator[FirewoodIntent | Travel]:
    home = routes.FIELDS.get(actor_id)
    actor = world.actors[actor_id]
    if home is None or actor.fatigue == 0 or actor.warm_until > world.minute:
        return
    site = actor.location
    if available(actor_id, FIREWOOD):
        if site == home:
            yield FirewoodIntent("burn_firewood", actor_id, HEARTH_MINUTES)
        else:
            yield routes.next_leg(world, actor_id, site, home)
    elif available(actor_id, COIN) >= FIREWOOD_PRICE and available(routes.stall(WOODCUTTER), FIREWOOD):
        if site == routes.MARKET_SQUARE:
            yield FirewoodIntent("buy_firewood", actor_id, world.config.village.purchase_minutes,
                                 price=FIREWOOD_PRICE)
        elif site == home:
            yield routes.next_leg(world, actor_id, site, routes.MARKET_SQUARE, grain=delivery_grain)
