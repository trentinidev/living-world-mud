"""Village charcoal production from wood bought at the shared stall."""

from __future__ import annotations

from collections.abc import Iterator

from . import forestry, routes
from .model import (
    CHARCOAL, CHARCOAL_CONTENT_VERSION, COIN, FIREWOOD, GRAIN, KILN_CONTENT_VERSIONS, Actor, CharcoalIntent,
    FirewoodIntent, Movement, Travel, World, WorldError,
)
from .routes import CHARCOAL_BURNER, KILN, MARKET_SQUARE, WOODCUTTER

KILN_STOCK = "kiln-stock"
BATCH_MINUTES = 160
FIREWOOD_PER_BATCH = 2
CHARCOAL_TARGET = 4
STARTING_COIN = 18


def add_kiln(world: World) -> None:
    if BATCH_MINUTES > world.config.max_action_minutes:
        raise WorldError("making charcoal takes longer than max_action_minutes")
    world.content_version = CHARCOAL_CONTENT_VERSION
    world.actors[CHARCOAL_BURNER] = Actor("Ash", KILN)
    world.inventory[CHARCOAL_BURNER] = {COIN: STARTING_COIN, GRAIN: 0, FIREWOOD: 0}
    world.inventory[KILN_STOCK] = {CHARCOAL: 0}


def validate(world: World, intent: CharcoalIntent) -> None:
    if world.content_version not in KILN_CONTENT_VERSIONS:
        raise WorldError("charcoal production requires a save with a kiln")
    actor = world.actors[intent.actor]
    if intent.actor != CHARCOAL_BURNER or actor.location != KILN or not actor.can_work:
        raise WorldError("only the charcoal burner can run a batch at the kiln")
    if intent.kind != "make_charcoal" or intent.duration != BATCH_MINUTES:
        raise WorldError("charcoal production requires the kiln batch duration")


def movements(intent: CharcoalIntent) -> tuple[Movement, ...]:
    return (
        Movement(intent.actor, None, FIREWOOD, FIREWOOD_PER_BATCH),
        Movement(None, KILN_STOCK, CHARCOAL, 1),
    )


def work(world: World, available: forestry.Available) -> Iterator[CharcoalIntent | FirewoodIntent | Travel]:
    actor = world.actors[CHARCOAL_BURNER]
    if not actor.can_work or available(KILN_STOCK, CHARCOAL) >= CHARCOAL_TARGET:
        return
    site = actor.location
    missing = FIREWOOD_PER_BATCH - available(CHARCOAL_BURNER, FIREWOOD)
    if missing <= 0:
        if site == KILN:
            yield CharcoalIntent("make_charcoal", CHARCOAL_BURNER, BATCH_MINUTES)
        else:
            yield routes.next_leg(world, CHARCOAL_BURNER, site, KILN)
        return

    coin = available(CHARCOAL_BURNER, COIN)
    if coin >= missing * forestry.FIREWOOD_PRICE and available(routes.stall(WOODCUTTER), FIREWOOD):
        if site == MARKET_SQUARE:
            yield FirewoodIntent("buy_firewood", CHARCOAL_BURNER, world.config.village.purchase_minutes,
                                 price=forestry.FIREWOOD_PRICE)
        else:
            yield routes.next_leg(world, CHARCOAL_BURNER, site, MARKET_SQUARE)
