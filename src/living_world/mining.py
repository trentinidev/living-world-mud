"""Finite ore extraction and stocking the market stall."""

from __future__ import annotations

from collections.abc import Iterator

from . import forestry, routes
from .model import (
    COIN, GRAIN, IRON_ORE, MINING_CONTENT_VERSION, ORE_IN_VEIN, Actor, MiningIntent, Movement,
    OreDelivery, Travel, World, WorldError, integer,
)
from .routes import MARKET_SQUARE, MINE, MINE_STOCK, MINER

DEPOSIT = "ore-deposit"
SHIFT_MINUTES = 100
SHIFT_LIMIT = 3
STALL_TARGET = 6
STARTING_COIN = 6


def add_mine(world: World) -> None:
    world.content_version = MINING_CONTENT_VERSION
    world.actors[MINER] = Actor("Bram", MINE)
    world.inventory[MINER] = {COIN: STARTING_COIN, GRAIN: 0}
    world.inventory[DEPOSIT] = {ORE_IN_VEIN: world.config.starting_ore_deposit}
    world.inventory[MINE_STOCK] = {IRON_ORE: 0}
    world.inventory[routes.stall(MINER)] = {IRON_ORE: 0}


def validate(world: World, intent: MiningIntent) -> None:
    if world.content_version != MINING_CONTENT_VERSION:
        raise WorldError("ore extraction requires a mining save")
    actor = world.actors[intent.actor]
    if intent.actor != MINER or actor.location != MINE or not actor.can_work:
        raise WorldError("only the miner can extract ore at the mine")
    if intent.kind != "mine_ore" or intent.duration != SHIFT_MINUTES:
        raise WorldError("ore extraction requires the mining shift duration")
    integer("mining quantity", intent.quantity, 1, SHIFT_LIMIT)


def movements(intent: MiningIntent) -> tuple[Movement, ...]:
    return (
        Movement(DEPOSIT, None, ORE_IN_VEIN, intent.quantity),
        Movement(None, MINE_STOCK, IRON_ORE, intent.quantity),
    )


def to_market(world: World, available: forestry.Available) -> Travel:
    duration = routes.distance(world, MINE, MARKET_SQUARE)
    quantity = min(available(MINE_STOCK, IRON_ORE),
                   STALL_TARGET - available(routes.stall(MINER), IRON_ORE))
    if quantity > 0:
        return OreDelivery(MINER, MINE, MARKET_SQUARE, duration, ore=quantity)
    return Travel(MINER, MINE, MARKET_SQUARE, duration)


def work(world: World, available: forestry.Available) -> Iterator[MiningIntent | Travel]:
    actor = world.actors[MINER]
    if not actor.can_work or available(routes.stall(MINER), IRON_ORE) >= STALL_TARGET:
        return
    remaining = available(DEPOSIT, ORE_IN_VEIN)
    stock = available(MINE_STOCK, IRON_ORE)
    if actor.location == MINE:
        if stock:
            yield to_market(world, available)
        elif remaining:
            yield MiningIntent("mine_ore", MINER, SHIFT_MINUTES, min(SHIFT_LIMIT, remaining))
    elif remaining or stock:
        yield routes.next_leg(world, MINER, actor.location, MINE)
