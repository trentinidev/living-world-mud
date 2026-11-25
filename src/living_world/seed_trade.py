"""Funded seed purchases at a neighboring farm and unloading at home."""

from collections.abc import Iterator

from . import routes
from .forestry import Available
from .model import COIN, SEED_GRAIN, SEED_TRADE_CONTENT_VERSIONS, Movement, SeedIntent, Travel, World, WorldError

SEED_PRICE = 2


def validate(world: World, intent: SeedIntent) -> None:
    fields = routes.fields_for(world)
    if world.content_version not in SEED_TRADE_CONTENT_VERSIONS or intent.actor not in fields:
        raise WorldError("seed trade requires a farm owner and a seed-trade save")
    site = world.actors[intent.actor].location
    if intent.kind == "buy_seed":
        seller = intent.seller
        if seller not in fields or seller == intent.actor or not world.actors[seller].alive:
            raise WorldError("seed purchases require a neighboring farm")
        if site != fields[seller] or intent.duration != world.config.village.purchase_minutes:
            raise WorldError("buying seed requires a purchase at the seller's farm")
    elif intent.kind == "store_seed":
        if site != fields[intent.actor] or intent.seller is not None or intent.duration != 1:
            raise WorldError("unloading seed requires one minute at the buyer's farm")
    else:
        raise WorldError(f"unknown seed activity {intent.kind!r}")


def has_surplus(world: World, seller: str, available: Available) -> bool:
    return available(routes.pantry(seller), SEED_GRAIN) > max(1, world.config.village.seed_reserve_target)


def movements(intent: SeedIntent) -> tuple[Movement, ...]:
    if intent.kind == "buy_seed":
        assert intent.seller is not None
        return (
            Movement(routes.pantry(intent.seller), intent.actor, SEED_GRAIN, 1),
            Movement(intent.actor, intent.seller, COIN, SEED_PRICE),
        )
    return (Movement(intent.actor, routes.pantry(intent.actor), SEED_GRAIN, 1),)


def procurement(world: World, buyer: str, available: Available) -> Iterator[SeedIntent | Travel]:
    site = world.actors[buyer].location
    fields = routes.fields_for(world)
    home = fields[buyer]
    if available(buyer, SEED_GRAIN):
        if site == home:
            yield SeedIntent("store_seed", buyer, 1)
        else:
            yield routes.next_leg(world, buyer, site, home)
        return
    if world.inventory[routes.pantry(buyer)][SEED_GRAIN] or available(buyer, COIN) < SEED_PRICE:
        return
    for seller, field in fields.items():
        if seller == buyer or not world.actors[seller].alive or not has_surplus(world, seller, available):
            continue
        if site == field:
            yield SeedIntent("buy_seed", buyer, world.config.village.purchase_minutes, seller)
        else:
            yield routes.next_leg(world, buyer, site, field)
