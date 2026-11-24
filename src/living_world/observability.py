"""Read-only summaries of committed inventory and journal entries."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict

from . import blacksmith, forestry, kiln, market, mining, routes, smelting
from .model import (
    BLACKSMITH_CONTENT_VERSIONS, CHARCOAL, COIN, FARMSTEAD, FIREWOOD, FORESTRY_CONTENT_VERSIONS,
    GRAIN, IRON, IRON_HOE, IRON_ORE, KILN_CONTENT_VERSIONS, MINING_CONTENT_VERSIONS, ORE_IN_VEIN,
    SEED_GRAIN, SEED_SAVING_CONTENT_VERSIONS, SEED_TRADE_CONTENT_VERSIONS, SMELTING_CONTENT_VERSIONS, SPATIAL_CONTENT_VERSIONS,
    STANDING_WOOD, TOOLS_CONTENT_VERSIONS, CharcoalDelivery, CharcoalIntent, FirewoodDelivery, ForgeIntent,
    HoeDelivery, IronDelivery, OreDelivery, SmeltingIntent, Travel, World,
)
from .routes import BLACKSMITH, CHARCOAL_BURNER, FARMS, MINE_STOCK, MINER, SMELTER, WOODCUTTER
from .village import hunger_at


def village_metrics(
    world: World, events: Iterable[tuple[int, str, dict]], available: market.Available | None = None,
) -> dict[str, object]:
    counts: Counter[str] = Counter()
    grain_produced = 0
    grain_eaten = 0
    wages = 0
    sales = 0
    harvests_by_farm = dict.fromkeys(FARMS, 0)
    purchases_by_seller = dict.fromkeys(FARMS, 0)
    prices_paid: Counter[str] = Counter()
    trips_by_road: Counter[str] = Counter()
    grain_delivered = 0
    wood_cut = 0
    wood_delivered = 0
    wood_burned = 0
    wood_sales_coins = 0
    heated_rests = 0
    firewood_for_kiln = 0
    firewood_for_hearths = 0
    kiln_paid = 0
    kiln_used_wood = 0
    charcoal_produced = 0
    ore_extracted = 0
    ore_delivered = 0
    charcoal_delivered = 0
    iron_delivered = 0
    industrial_purchases: Counter[str] = Counter()
    industrial_payments: Counter[str] = Counter()
    smelting_inputs: Counter[str] = Counter()
    iron_produced = 0
    forging_inputs: Counter[str] = Counter()
    hoes_forged = 0
    hoes_delivered = 0
    hoes_worn_out = 0
    assisted_harvests = 0
    bonus_grain = 0
    seeds_planted = 0
    seeds_saved = 0
    seed_purchase_coins = 0
    installed_by_farm: Counter[str] = Counter()
    travel_minutes = 0
    shocks: list[dict[str, object]] = []
    for minute, kind, payload in events:
        counts[kind] += 1
        if "farm" in payload:
            if kind == "harvest_completed":
                harvests_by_farm[payload["farm"]] += 1
            elif kind == "buy_food_completed":
                purchases_by_seller[payload["farm"]] += 1
                prices_paid[str(payload["price"])] += 1
        if kind in ("seed_shortage", "worker_sidelined"):
            shocks.append({"minute": minute, "kind": kind, **payload})
        if kind == "travel_completed":
            field = payload["destination"] if payload["origin"] == routes.MARKET_SQUARE else payload["origin"]
            trips_by_road[field] += 1
            travel_minutes += payload["duration"]
        if kind == "rest_completed" and payload["needs"].get("heated"):
            heated_rests += 1
        if kind == "buy_firewood_completed":
            if payload["actor"] == CHARCOAL_BURNER:
                firewood_for_kiln += 1
            elif payload["actor"] in FARMS:
                firewood_for_hearths += 1
        if kind == "install_hoe_completed":
            installed_by_farm[payload["actor"]] += 1
        if kind == "harvest_completed" and "hoe_bonus_grain" in payload:
            assisted_harvests += 1
            bonus_grain += payload["hoe_bonus_grain"]
        for movement in payload.get("movements", ()):
            good, quantity = movement["good"], movement["quantity"]
            if kind == "harvest_completed":
                if good == GRAIN:
                    grain_produced += quantity
                elif good == SEED_GRAIN:
                    if movement["source"] is None:
                        seeds_saved += quantity
                    else:
                        seeds_planted += quantity
                elif good == COIN:
                    wages += quantity
                elif good == IRON_HOE:
                    hoes_worn_out += quantity
            elif kind == "eat_completed":
                grain_eaten += quantity
            elif kind == "buy_food_completed" and good == COIN:
                sales += quantity
            elif kind == "buy_seed_completed" and good == COIN:
                seed_purchase_coins += quantity
            elif kind == "travel_completed":
                if good == GRAIN:
                    grain_delivered += quantity
                elif good == FIREWOOD:
                    wood_delivered += quantity
                elif good == IRON_ORE:
                    ore_delivered += quantity
                elif good == CHARCOAL:
                    charcoal_delivered += quantity
                elif good == IRON:
                    iron_delivered += quantity
                elif good == IRON_HOE:
                    hoes_delivered += quantity
            elif kind == "cut_wood_completed" and good == FIREWOOD:
                wood_cut += quantity
            elif kind == "burn_firewood_completed" and good == FIREWOOD:
                wood_burned += quantity
            elif kind == "buy_firewood_completed" and good == COIN:
                wood_sales_coins += quantity
                if payload["actor"] == CHARCOAL_BURNER:
                    kiln_paid += quantity
            elif kind == "make_charcoal_completed":
                if good == FIREWOOD:
                    kiln_used_wood += quantity
                elif good == CHARCOAL:
                    charcoal_produced += quantity
            elif kind == "mine_ore_completed" and good == IRON_ORE:
                ore_extracted += quantity
            elif kind in ("buy_iron_ore_completed", "buy_charcoal_completed", "buy_iron_completed", "buy_hoe_completed"):
                if good == COIN:
                    industrial_payments[kind] += quantity
                else:
                    industrial_purchases[good] += quantity
            elif kind == "smelt_iron_completed":
                if good == IRON:
                    iron_produced += quantity
                else:
                    smelting_inputs[good] += quantity
            elif kind == "forge_hoe_completed":
                if good == IRON_HOE:
                    hoes_forged += quantity
                else:
                    forging_inputs[good] += quantity
    metrics: dict[str, object] = {
        "grain_produced": grain_produced,
        "grain_eaten": grain_eaten,
        "grain_in_stock": sum(stock.get(GRAIN, 0) for stock in world.inventory.values()),
        "seed_in_stock": sum(stock.get(SEED_GRAIN, 0) for stock in world.inventory.values()),
        "coin_supply": sum(stock.get(COIN, 0) for stock in world.inventory.values()),
        "coin_paid_in_wages": wages,
        "coin_paid_for_food": sales,
        "harvests": counts["harvest_completed"],
        "purchases": counts["buy_food_completed"],
        "rests": counts["rest_completed"],
        "waits": counts["decision_waited"],
        "failed_actions": counts["action_failed"],
        "needs": {
            key: {"hunger": hunger_at(actor, world.minute, world.config.village),
                  "fatigue": actor.fatigue}
            for key, actor in world.actors.items()
        },
    }
    if available is not None:
        spatial = world.content_version in SPATIAL_CONTENT_VERSIONS
        metrics["market"] = {
            "offers": [asdict(offer) for offer in market.offers(world, available)],
            "harvests_by_farm": harvests_by_farm,
            "purchases_by_seller": purchases_by_seller,
            "prices_paid": dict(prices_paid),
            "available_farmhands": sum(
                actor.can_work and actor.alive and (spatial or actor.location == FARMSTEAD)
                for key, actor in world.actors.items() if key.startswith("farmhand-")
            ),
            "shocks": shocks,
        }
        if spatial:
            metrics["travel"] = {
                "roads_to_market": routes.roads_for(world).copy(),
                "completed_trips": counts["travel_completed"],
                "trips_by_road": dict(trips_by_road),
                "travel_minutes": travel_minutes,
                "grain_delivered": grain_delivered,
                "last_reached_locations": {key: actor.location for key, actor in world.actors.items()},
                "in_transit": {
                    action.intent.actor: {
                        "origin": action.intent.source,
                        "destination": action.intent.destination,
                        "arrives_at": action.finishes_at,
                        "grain": action.intent.grain,
                        **({"firewood": action.intent.firewood}
                           if isinstance(action.intent, FirewoodDelivery) else {}),
                        **({"ore": action.intent.ore} if isinstance(action.intent, OreDelivery) else {}),
                        **({"charcoal": action.intent.charcoal}
                           if isinstance(action.intent, CharcoalDelivery) else {}),
                        **({"iron": action.intent.iron} if isinstance(action.intent, IronDelivery) else {}),
                        **({"hoes": action.intent.hoes} if isinstance(action.intent, HoeDelivery) else {}),
                    }
                    for action in world.actions.values()
                    if action.status == "started" and isinstance(action.intent, Travel)
                },
            }
        if world.content_version in FORESTRY_CONTENT_VERSIONS:
            stall_stock = available(routes.stall(WOODCUTTER), FIREWOOD)
            metrics["forestry"] = {
                "standing_wood": world.inventory[forestry.WOODLAND_STOCK][STANDING_WOOD],
                "firewood_cut": wood_cut,
                "firewood_delivered": wood_delivered,
                "firewood_sold": counts["buy_firewood_completed"],
                "firewood_burned": wood_burned,
                "firewood_in_stock": sum(stock.get(FIREWOOD, 0) for stock in world.inventory.values()),
                "coin_paid_for_firewood": wood_sales_coins,
                "market_offer": (
                    {"seller": WOODCUTTER, "quantity": stall_stock, "price": forestry.FIREWOOD_PRICE}
                    if stall_stock and world.actors[WOODCUTTER].alive else None
                ),
                "heated_rests": heated_rests,
                "hearths": {
                    farm: {"warm_until": world.actors[farm].warm_until,
                           "warm": world.actors[farm].warm_until > world.minute}
                    for farm in FARMS
                },
            }
        if world.content_version in KILN_CONTENT_VERSIONS:
            wallet = world.inventory[CHARCOAL_BURNER]
            metrics["charcoal"] = {
                "firewood_bought_by_kiln": firewood_for_kiln,
                "firewood_bought_by_households": firewood_for_hearths,
                "coins_paid_by_kiln": kiln_paid,
                "firewood_used_at_kiln": kiln_used_wood,
                "firewood_carried_by_burner": wallet[FIREWOOD],
                "batches_completed": counts["make_charcoal_completed"],
                "charcoal_produced": charcoal_produced,
                "charcoal_in_stock": world.inventory[kiln.KILN_STOCK][CHARCOAL],
                "burner_coins": wallet[COIN],
                "batch_finishes_at": next(
                    (action.finishes_at for action in world.actions.values()
                     if action.status == "started" and isinstance(action.intent, CharcoalIntent)),
                    None,
                ),
            }
        if world.content_version in MINING_CONTENT_VERSIONS:
            metrics["mining"] = {
                "deposit_remaining": world.inventory[mining.DEPOSIT][ORE_IN_VEIN],
                "ore_extracted": ore_extracted,
                "ore_delivered": ore_delivered,
                "ore_at_mine": world.inventory[MINE_STOCK][IRON_ORE],
                "ore_at_market": world.inventory[routes.stall(MINER)][IRON_ORE],
                "delivery_arrives_at": next(
                    (action.finishes_at for action in world.actions.values()
                     if action.status == "started" and isinstance(action.intent, OreDelivery)),
                    None,
                ),
            }
        if world.content_version in SMELTING_CONTENT_VERSIONS:
            metrics["smelting"] = {
                "ore_purchased": industrial_purchases[IRON_ORE],
                "charcoal_purchased": industrial_purchases[CHARCOAL],
                "coins_paid_to_miner": industrial_payments["buy_iron_ore_completed"],
                "coins_paid_to_charcoal_burner": industrial_payments["buy_charcoal_completed"],
                "charcoal_delivered": charcoal_delivered,
                "charcoal_at_market": world.inventory[routes.stall(CHARCOAL_BURNER)][CHARCOAL],
                "ore_consumed": smelting_inputs[IRON_ORE],
                "charcoal_consumed": smelting_inputs[CHARCOAL],
                "iron_produced": iron_produced,
                "iron_in_stock": world.inventory[smelting.IRON_STOCK][IRON],
                "smelter_coins": world.inventory[SMELTER][COIN],
                "batch_finishes_at": next(
                    (action.finishes_at for action in world.actions.values()
                     if action.status == "started" and isinstance(action.intent, SmeltingIntent)
                     and action.intent.kind == "smelt_iron"),
                    None,
                ),
            }
        if world.content_version in BLACKSMITH_CONTENT_VERSIONS:
            metrics["blacksmith"] = {
                "iron_delivered": iron_delivered,
                "iron_at_market": world.inventory[routes.stall(SMELTER)][IRON],
                "iron_purchased": industrial_purchases[IRON],
                "coins_paid_to_smelter": industrial_payments["buy_iron_completed"],
                "iron_consumed": forging_inputs[IRON],
                "hoes_forged": hoes_forged,
                "hoes_in_stock": world.inventory[blacksmith.TOOL_STOCK][IRON_HOE],
                "blacksmith_coins": world.inventory[BLACKSMITH][COIN],
                "forge_finishes_at": next(
                    (action.finishes_at for action in world.actions.values()
                     if action.status == "started" and isinstance(action.intent, ForgeIntent)
                     and action.intent.kind == "forge_hoe"),
                    None,
                ),
            }
        if world.content_version in TOOLS_CONTENT_VERSIONS:
            metrics["tools"] = {
                "hoes_delivered": hoes_delivered,
                "hoes_at_market": world.inventory[routes.stall(BLACKSMITH)][IRON_HOE],
                "hoes_bought": industrial_purchases[IRON_HOE],
                "coins_paid_to_blacksmith": industrial_payments["buy_hoe_completed"],
                "hoes_installed": sum(installed_by_farm.values()),
                "hoes_worn_out": hoes_worn_out,
                "replacement_hoes_installed": sum(count - 1 for count in installed_by_farm.values()),
                "assisted_harvests": assisted_harvests,
                "bonus_grain": bonus_grain,
                "remaining_uses_by_farm": world.hoe_uses.copy(),
            }
        if world.content_version in SEED_SAVING_CONTENT_VERSIONS:
            metrics["seed_saving"] = {
                "reserve_target": world.config.village.seed_reserve_target,
                "seeds_planted": seeds_planted,
                "seeds_saved": seeds_saved,
                "seed_by_farm": {
                    farm: world.inventory[routes.pantry(farm)][SEED_GRAIN] for farm in FARMS
                },
                "food_grain_harvested": grain_produced,
                "total_grain_harvested": grain_produced + seeds_saved,
            }
        if world.content_version in SEED_TRADE_CONTENT_VERSIONS:
            metrics["seed_trade"] = {
                "seeds_purchased": counts["buy_seed_completed"],
                "coins_paid_for_seed": seed_purchase_coins,
                "seeds_unloaded": counts["store_seed_completed"],
                "seeds_carried_by_farm": {
                    farm: world.inventory[farm].get(SEED_GRAIN, 0) for farm in FARMS
                },
            }
    return metrics
