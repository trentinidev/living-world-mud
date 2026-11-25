"""The village roads and the storage accounts attached to each site."""

from __future__ import annotations

from dataclasses import replace

from .model import (
    BLACKSMITH_CONTENT_VERSIONS, CHARCOAL, CHARCOAL_CONTENT_VERSION, FARM_OWNER, FIREWOOD,
    FORESTRY_CONTENT_VERSIONS, GRAIN, HAMLET_CONTENT_VERSION, IRON, IRON_HOE, IRON_ORE, MAX_QUANTITY,
    MINING_CONTENT_VERSIONS,
    ROUTES_CONTENT_VERSION, SEED_GRAIN, SMELTING_CONTENT_VERSIONS, SPATIAL_CONTENT_VERSIONS,
    TOOLS_CONTENT_VERSIONS, Actor, CharcoalDelivery, FirewoodDelivery, HoeDelivery, IronDelivery, Movement,
    OreDelivery, Travel, World, WorldError, integer,
)

WEST_FARM = "west-farm-owner"
FARMS = (FARM_OWNER, WEST_FARM)
MARKET_SQUARE = "market-square"
FIELDS = {FARM_OWNER: "east-farm", WEST_FARM: "west-farm"}
ROADS = {FIELDS[FARM_OWNER]: 20, FIELDS[WEST_FARM]: 45}
WOODCUTTER = "woodcutter"
WOODLAND = "woodland"
WOODPILE = "woodcutter-woodpile"
WOODLAND_ROADS = ROADS | {WOODLAND: 35}
CHARCOAL_BURNER = "charcoal-burner"
KILN = "kiln"
KILN_STOCK = "kiln-stock"
KILN_ROADS = WOODLAND_ROADS | {KILN: 25}
MINER = "miner"
MINE = "mine"
MINE_STOCK = "mine-stock"
MINE_ROADS = KILN_ROADS | {MINE: 40}
SMELTER = "smelter"
SMELTERY = "smeltery"
IRON_STOCK = "smeltery-stock"
SMELTERY_ROADS = MINE_ROADS | {SMELTERY: 30}
BLACKSMITH = "blacksmith"
FORGE = "forge"
TOOL_STOCK = "forge-stock"
FORGE_ROADS = SMELTERY_ROADS | {FORGE: 15}
HAMLET_FARM_SITES = (
    ("north-farm-owner", "Edda", "north-farm", 25),
    ("south-farm-owner", "Leif", "south-farm", 30),
    ("hill-farm-owner", "Hilda", "hill-farm", 40),
    ("river-farm-owner", "Runa", "river-farm", 35),
)


def extra_farm_sites(world: World) -> tuple[tuple[str, str, str, int], ...]:
    if world.content_version != HAMLET_CONTENT_VERSION:
        return ()
    return HAMLET_FARM_SITES[:world.config.hamlet.farms - len(FARMS)]


def fields_for(world: World) -> dict[str, str]:
    extra = extra_farm_sites(world)
    return FIELDS | {owner: field for owner, _, field, _ in extra} if extra else FIELDS


def add_hamlet_farms(world: World) -> None:
    for owner, name, field, minutes in extra_farm_sites(world):
        if minutes > world.config.max_action_minutes:
            raise WorldError("a road is longer than max_action_minutes")
        world.actors[owner] = Actor(name, field)
        world.inventory[owner] = world.inventory[FARM_OWNER].copy()
        world.inventory[pantry(owner)] = world.inventory[pantry(FARM_OWNER)].copy()
        world.inventory[stall(owner)] = world.inventory[stall(FARM_OWNER)].copy()
        world.hoe_uses[owner] = 0


def pantry(farm: str) -> str:
    return f"{farm}-pantry"


def stall(farm: str) -> str:
    return f"{farm}-stall"


def separate_sites(world: World) -> None:
    if max(ROADS.values()) > world.config.max_action_minutes:
        raise WorldError("a road is longer than max_action_minutes")
    world.content_version = ROUTES_CONTENT_VERSION
    for actor, state in world.actors.items():
        world.actors[actor] = replace(state, location=FIELDS.get(actor, MARKET_SQUARE))
    for farm in FARMS:
        inventory = world.inventory[farm]
        world.inventory[pantry(farm)] = {GRAIN: inventory[GRAIN], SEED_GRAIN: inventory.pop(SEED_GRAIN)}
        world.inventory[stall(farm)] = {GRAIN: 0}
        inventory[GRAIN] = 0


def roads_for(world: World) -> dict[str, int]:
    if world.content_version in BLACKSMITH_CONTENT_VERSIONS:
        extra = extra_farm_sites(world)
        return FORGE_ROADS | {field: minutes for _, _, field, minutes in extra} if extra else FORGE_ROADS
    if world.content_version in SMELTING_CONTENT_VERSIONS:
        return SMELTERY_ROADS
    if world.content_version in MINING_CONTENT_VERSIONS:
        return MINE_ROADS
    if world.content_version == CHARCOAL_CONTENT_VERSION:
        return KILN_ROADS
    if world.content_version in FORESTRY_CONTENT_VERSIONS:
        return WOODLAND_ROADS
    return ROADS


def distance(world: World, source: str, destination: str) -> int:
    roads = roads_for(world)
    return 0 if source == destination else roads.get(source, 0) + roads.get(destination, 0)


def next_leg(world: World, actor: str, source: str, destination: str, *, grain: int = 0) -> Travel:
    stop = destination if source == MARKET_SQUARE else MARKET_SQUARE
    return Travel(actor, source, stop, distance(world, source, stop), grain)


def validate_travel(world: World, intent: Travel) -> None:
    if world.content_version not in SPATIAL_CONTENT_VERSIONS:
        raise WorldError("travel requires a save with roads")
    if not isinstance(intent.source, str) or not isinstance(intent.destination, str):
        raise WorldError("travel locations must be location IDs")
    if intent.source != world.actors[intent.actor].location:
        raise WorldError("travel must start at the actor's current location")
    if intent.source == MARKET_SQUARE:
        field = intent.destination
    elif intent.destination == MARKET_SQUARE:
        field = intent.source
    else:
        raise WorldError("no direct road connects these locations")
    roads = roads_for(world)
    if field not in roads:
        raise WorldError("no direct road connects these locations")
    if intent.duration != roads[field]:
        raise WorldError(f"this road takes {roads[field]} simulated minutes")
    integer("travel grain", intent.grain, 0, MAX_QUANTITY)
    if intent.grain and (fields_for(world).get(intent.actor) != intent.source or intent.destination != MARKET_SQUARE):
        raise WorldError("farmers can only deliver grain from their own pantry to their market stall")
    if isinstance(intent, FirewoodDelivery):
        if (world.content_version not in FORESTRY_CONTENT_VERSIONS or intent.actor != WOODCUTTER
                or intent.source != WOODLAND or intent.destination != MARKET_SQUARE):
            raise WorldError("firewood deliveries must go from the woodland to the woodcutter's stall")
        integer("delivery firewood", intent.firewood, 1, MAX_QUANTITY)
    elif isinstance(intent, OreDelivery):
        if (world.content_version not in MINING_CONTENT_VERSIONS or intent.actor != MINER
                or intent.source != MINE or intent.destination != MARKET_SQUARE):
            raise WorldError("ore deliveries must go from the mine to the miner's stall")
        integer("delivery ore", intent.ore, 1, MAX_QUANTITY)
    elif isinstance(intent, CharcoalDelivery):
        if (world.content_version not in SMELTING_CONTENT_VERSIONS or intent.actor != CHARCOAL_BURNER
                or intent.source != KILN or intent.destination != MARKET_SQUARE):
            raise WorldError("charcoal deliveries must go from the kiln to the charcoal burner's stall")
        integer("delivery charcoal", intent.charcoal, 1, MAX_QUANTITY)
    elif isinstance(intent, IronDelivery):
        if (world.content_version not in BLACKSMITH_CONTENT_VERSIONS or intent.actor != SMELTER
                or intent.source != SMELTERY or intent.destination != MARKET_SQUARE):
            raise WorldError("iron deliveries must go from the smeltery to the smelter's stall")
        integer("delivery iron", intent.iron, 1, MAX_QUANTITY)
    elif isinstance(intent, HoeDelivery):
        if (world.content_version not in TOOLS_CONTENT_VERSIONS or intent.actor != BLACKSMITH
                or intent.source != FORGE or intent.destination != MARKET_SQUARE):
            raise WorldError("hoe deliveries must go from the forge to the blacksmith's stall")
        integer("delivery hoes", intent.hoes, 1, MAX_QUANTITY)


def movements(intent: Travel) -> tuple[Movement, ...]:
    if isinstance(intent, FirewoodDelivery):
        return (Movement(WOODPILE, stall(WOODCUTTER), FIREWOOD, intent.firewood),)
    if isinstance(intent, OreDelivery):
        return (Movement(MINE_STOCK, stall(MINER), IRON_ORE, intent.ore),)
    if isinstance(intent, CharcoalDelivery):
        return (Movement(KILN_STOCK, stall(CHARCOAL_BURNER), CHARCOAL, intent.charcoal),)
    if isinstance(intent, IronDelivery):
        return (Movement(IRON_STOCK, stall(SMELTER), IRON, intent.iron),)
    if isinstance(intent, HoeDelivery):
        return (Movement(TOOL_STOCK, stall(BLACKSMITH), IRON_HOE, intent.hoes),)
    if intent.grain:
        return (Movement(pantry(intent.actor), stall(intent.actor), GRAIN, intent.grain),)
    return ()
