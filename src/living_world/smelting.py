"""Funded purchases of industrial inputs and timed iron batches."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from . import forestry, routes
from .model import (
    BLACKSMITH_CONTENT_VERSIONS, CHARCOAL, COIN, GRAIN, IRON, IRON_ORE, SMELTING_CONTENT_VERSION,
    SMELTING_CONTENT_VERSIONS, Actor, IronDelivery, Movement, SmeltingIntent, Travel, World,
    WorldError,
)
from .routes import CHARCOAL_BURNER, IRON_STOCK, MARKET_SQUARE, MINER, SMELTER, SMELTERY

BATCH_MINUTES = 180
IRON_TARGET = 4
STARTING_COIN = 42


@dataclass(frozen=True, slots=True)
class SmeltingInput:
    good: str
    seller: str
    units: int
    price: int


Purchase = Literal["buy_iron_ore", "buy_charcoal"]
INPUTS: dict[Purchase, SmeltingInput] = {
    "buy_iron_ore": SmeltingInput(IRON_ORE, MINER, 2, 2),
    "buy_charcoal": SmeltingInput(CHARCOAL, CHARCOAL_BURNER, 1, 5),
}


def add_smeltery(world: World) -> None:
    if BATCH_MINUTES > world.config.max_action_minutes:
        raise WorldError("smelting takes longer than max_action_minutes")
    world.content_version = SMELTING_CONTENT_VERSION
    world.actors[SMELTER] = Actor("Mara", SMELTERY)
    world.inventory[SMELTER] = {COIN: STARTING_COIN, GRAIN: 0, IRON_ORE: 0, CHARCOAL: 0}
    world.inventory[routes.stall(CHARCOAL_BURNER)] = {CHARCOAL: 0}
    world.inventory[IRON_STOCK] = {IRON: 0}


def validate(world: World, intent: SmeltingIntent) -> None:
    if world.content_version not in SMELTING_CONTENT_VERSIONS:
        raise WorldError("industrial purchases and smelting require a save with a smeltery")
    actor = world.actors[intent.actor]
    if intent.kind == "smelt_iron":
        if intent.actor != SMELTER or actor.location != SMELTERY or not actor.can_work:
            raise WorldError("only the smelter can run a batch at the smeltery")
        if intent.duration != BATCH_MINUTES or intent.price is not None:
            raise WorldError("smelting requires the batch duration")
        return

    material = INPUTS.get(intent.kind)
    if material is None:
        raise WorldError(f"unknown smelting activity {intent.kind!r}")
    if actor.location != MARKET_SQUARE or intent.actor == material.seller:
        raise WorldError("buying smelting inputs requires a customer at the market square")
    if not world.actors[material.seller].alive:
        raise WorldError(f"the {material.seller}'s stall is closed")
    if type(intent.price) is not int or intent.price != material.price:
        raise WorldError(f"{material.good} costs {material.price} coins per unit")
    if intent.duration != world.config.village.purchase_minutes:
        raise WorldError("duration does not match the industrial purchase rules")


def movements(intent: SmeltingIntent) -> tuple[Movement, ...]:
    if intent.kind == "smelt_iron":
        inputs = tuple(
            Movement(intent.actor, None, material.good, material.units)
            for material in INPUTS.values()
        )
        return (*inputs, Movement(None, IRON_STOCK, IRON, 1))

    material = INPUTS[intent.kind]
    return (
        Movement(routes.stall(material.seller), intent.actor, material.good, 1),
        Movement(intent.actor, material.seller, COIN, material.price),
    )


def to_market(world: World, available: forestry.Available) -> Travel:
    duration = routes.distance(world, SMELTERY, MARKET_SQUARE)
    quantity = min(available(IRON_STOCK, IRON), IRON_TARGET - available(routes.stall(SMELTER), IRON))
    if quantity > 0:
        return IronDelivery(SMELTER, SMELTERY, MARKET_SQUARE, duration, iron=quantity)
    return Travel(SMELTER, SMELTERY, MARKET_SQUARE, duration)


def work(world: World, available: forestry.Available) -> Iterator[SmeltingIntent | Travel]:
    actor = world.actors[SMELTER]
    if not actor.can_work:
        return
    local_stock = available(IRON_STOCK, IRON)
    if world.content_version in BLACKSMITH_CONTENT_VERSIONS:
        if available(routes.stall(SMELTER), IRON) >= IRON_TARGET:
            return
        if local_stock:
            if actor.location == SMELTERY:
                yield to_market(world, available)
            else:
                yield routes.next_leg(world, SMELTER, actor.location, SMELTERY)
            return
    elif local_stock >= IRON_TARGET:
        return
    missing = [
        (kind, material, material.units - available(SMELTER, material.good))
        for kind, material in INPUTS.items()
        if available(SMELTER, material.good) < material.units
    ]
    if not missing:
        if actor.location == SMELTERY:
            yield SmeltingIntent("smelt_iron", SMELTER, BATCH_MINUTES)
        else:
            yield routes.next_leg(world, SMELTER, actor.location, SMELTERY)
    elif available(SMELTER, COIN) >= sum(quantity * material.price for _, material, quantity in missing):
        for kind, material, _ in missing:
            if world.actors[material.seller].alive and available(routes.stall(material.seller), material.good):
                if actor.location == MARKET_SQUARE:
                    yield SmeltingIntent(kind, SMELTER, world.config.village.purchase_minutes,
                                         price=material.price)
                else:
                    yield routes.next_leg(world, SMELTER, actor.location, MARKET_SQUARE)
                    return
