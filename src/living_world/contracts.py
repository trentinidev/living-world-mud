"""Funded market orders for a particular quality of hoe."""

from collections.abc import Iterator
from dataclasses import replace

from . import farm_tools, routes
from .forestry import Available
from .model import (
    COIN, CONTRACTS_CONTENT_VERSIONS, IRON_HOE, HoeOrder, Movement, OrderIntent,
    Travel, World, WorldError,
)

PRICE = 19
MIN_QUALITY = 40
OPEN_STATUSES = ("open", "accepted")


def escrow(farm: str) -> str:
    return f"{farm}-escrow"


def has_order(world: World, farm: str) -> bool:
    return any(order.farm == farm and order.status in OPEN_STATUSES for order in world.hoe_orders.values())


def needs_hoe(world: World, farm: str) -> bool:
    return (not farm_tools.usable(world, farm)
            and not world.inventory[farm][IRON_HOE]
            and not world.inventory[routes.stall(farm)].get(IRON_HOE)
            and not has_order(world, farm))


def supplier_stock(actor: str) -> str:
    return routes.stall(actor) if actor == routes.BLACKSMITH else actor


def eligible_item(world: World, actor: str) -> str | None:
    account = supplier_stock(actor)
    return min(
        (item for item, record in world.crafted_hoes.items()
         if record.account == account and record.quality >= MIN_QUALITY),
        key=lambda item: int(item.removeprefix("hoe-")),
        default=None,
    )


def validate(world: World, intent: OrderIntent) -> None:
    if world.content_version not in CONTRACTS_CONTENT_VERSIONS:
        raise WorldError("hoe orders require the contracts scenario")
    if intent.duration != 1 or world.actors[intent.actor].location != routes.MARKET_SQUARE:
        raise WorldError("hoe order actions take one minute at the market square")
    if intent.kind in ("post_order", "collect_order"):
        if intent.actor not in routes.fields_for(world) or intent.order_id is not None or intent.item_id is not None:
            raise WorldError("only farm owners can post orders or collect their deliveries")
        if intent.kind == "post_order" and not needs_hoe(world, intent.actor):
            raise WorldError("the farm already has a hoe or an active order")
        return

    order = world.hoe_orders.get(intent.order_id)
    if order is None:
        raise WorldError("unknown hoe order")
    if world.minute >= order.deadline or order.status not in OPEN_STATUSES:
        raise WorldError("the hoe order is closed")
    if intent.actor == order.farm:
        raise WorldError("a farm owner cannot fill their own order")
    if intent.kind == "accept_order":
        if order.status != "open" or intent.item_id is not None:
            raise WorldError("the hoe order is already assigned")
        return
    if intent.kind != "deliver_order" or order.status != "accepted" or order.supplier != intent.actor:
        raise WorldError("only the assigned supplier can deliver this order")
    item = world.crafted_hoes.get(intent.item_id)
    if item is None or item.account != supplier_stock(intent.actor) or item.quality < MIN_QUALITY:
        raise WorldError(f"delivery requires a hoe in your stock with quality {MIN_QUALITY} or higher")


def movements(world: World, intent: OrderIntent) -> tuple[Movement, ...]:
    if intent.kind == "post_order":
        return (Movement(intent.actor, escrow(intent.actor), COIN, PRICE),)
    if intent.kind == "collect_order":
        return (Movement(routes.stall(intent.actor), intent.actor, IRON_HOE, 1),)
    if intent.kind == "deliver_order":
        assert intent.order_id is not None
        farm = world.hoe_orders[intent.order_id].farm
        return (
            Movement(supplier_stock(intent.actor), routes.stall(farm), IRON_HOE, 1),
            Movement(escrow(farm), intent.actor, COIN, PRICE),
        )
    return ()


def apply(world: World, intent: OrderIntent) -> tuple[str, HoeOrder]:
    if intent.kind == "post_order":
        event = world.next_event_id
        order_id = f"order-{event}"
        order = HoeOrder(intent.actor, world.minute + 2 * world.config.minutes_per_day, event)
    else:
        order_id = intent.order_id
        assert order_id is not None
        previous = world.hoe_orders[order_id]
        if intent.kind == "accept_order":
            order = replace(previous, status="accepted", supplier=intent.actor)
        else:
            order = replace(previous, status="delivered", item_id=intent.item_id)
    world.hoe_orders[order_id] = order
    return order_id, order


def farm_choices(world: World, farm: str, available: Available) -> Iterator[OrderIntent | Travel]:
    site = world.actors[farm].location
    if available(routes.stall(farm), IRON_HOE):
        if site == routes.MARKET_SQUARE:
            yield OrderIntent("collect_order", farm)
        else:
            yield routes.next_leg(world, farm, site, routes.MARKET_SQUARE)
    elif (site == routes.MARKET_SQUARE and needs_hoe(world, farm)
          and available(routes.stall(routes.BLACKSMITH), IRON_HOE) == 0
          and available(farm, COIN) >= PRICE + world.config.village.meal_price):
        yield OrderIntent("post_order", farm)


def smith_choices(world: World, available: Available) -> Iterator[OrderIntent | Travel]:
    if not available(routes.stall(routes.BLACKSMITH), IRON_HOE):
        return
    item = eligible_item(world, routes.BLACKSMITH)
    if item is None:
        return
    for key, order in sorted(world.hoe_orders.items(), key=lambda pair: (pair[1].deadline, pair[0])):
        if order.status == "open" or (order.status == "accepted" and order.supplier == routes.BLACKSMITH):
            site = world.actors[routes.BLACKSMITH].location
            if site != routes.MARKET_SQUARE:
                yield routes.next_leg(world, routes.BLACKSMITH, site, routes.MARKET_SQUARE)
            elif order.status == "open":
                yield OrderIntent("accept_order", routes.BLACKSMITH, order_id=key)
            else:
                yield OrderIntent("deliver_order", routes.BLACKSMITH, order_id=key, item_id=item)
