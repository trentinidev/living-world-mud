"""Text commands that read the save or submit actions to the simulation."""

from __future__ import annotations

from . import blacksmith, contracts, craftsmanship, farm_tools, forestry, market, routes, village
from .model import (
    APPRENTICESHIP_CONTENT_VERSION, CIVILIAN_CONTENT_VERSIONS, COIN, CONTRACTS_CONTENT_VERSIONS,
    FIREWOOD, IRON, FirewoodIntent,
    ForgeIntent, MarketIntent, OrderIntent, PersonalForge, Travel, VillageIntent, WorldError, integer,
)
from .persistence import Save
from .simulation import PLAYER_ACTION_PREFIX, Simulation

HELP = """Commands
  look             See your location and roads.
  inventory        See what you carry, hunger, and fatigue.
  go <location>    Travel along one road.
  market           See offers while at the market square.
  buy [seller]     Buy one grain. Defaults to the cheapest offer.
  buy iron         Buy one bar at the civilian market.
  buy firewood     Buy one bundle at the civilian market.
  work             Take a paid shift at a farm or the civilian forge.
  craft hoe        Rent the forge and use your own iron and firewood.
  learn hammer     Pay for a lesson with Ada at the apprenticeship forge.
  craft hammer      Forge a hammer once you've learned the recipe.
  sell hoe         Sell your oldest hoe to Ada at the market.
  orders           See available or assigned hoe orders in the contracts scenario.
  accept <order>   Take a funded hoe order at the market square.
  deliver <order>  Hand over a qualifying hoe and collect the payment.
  skills           See your blacksmithing experience.
  eat              Eat one grain from your inventory.
  rest             Rest to recover from work.
  wait <minutes>   Let time pass.
  help             Show these commands.
  quit             Close the text interface."""

COMMAND_ARGUMENTS = {
    "look": (0, 0), "inventory": (0, 0), "market": (0, 0),
    "go": (1, 1), "buy": (0, 1), "work": (0, 0), "eat": (0, 0),
    "rest": (0, 0), "wait": (1, 1), "skills": (0, 0), "craft": (1, 1), "sell": (1, 1),
    "orders": (0, 0), "accept": (1, 1), "deliver": (1, 1), "learn": (1, 1),
}


def character(sim: Simulation) -> str:
    player = sim.world.player_id
    if player is None:
        raise WorldError("this save has no player character. Create a new save with --player NAME")
    return player


def look(sim: Simulation) -> str:
    world = sim.world
    player = character(sim)
    actor = world.actors[player]
    trip = sim.active.get(player)
    if trip and isinstance(trip.intent, Travel):
        return f"Minute {world.minute}. {actor.name} is traveling to {trip.intent.destination}."
    roads = routes.roads_for(world)
    exits = roads if actor.location == routes.MARKET_SQUARE else {routes.MARKET_SQUARE: roads[actor.location]}
    directions = ", ".join(f"{site} ({minutes} min)" for site, minutes in sorted(exits.items()))
    lines = [f"Minute {world.minute}. {actor.name} is at {actor.location}.", f"Roads: {directions}"]
    if world.content_version in CIVILIAN_CONTENT_VERSIONS and actor.location == routes.FORGE:
        if not sim.forge_open():
            lines.append("The forge is occupied.")
        elif blacksmith.can_hire(world, sim.available):
            lines.append("Paid shift available. Type work.")
        else:
            lines.append("The forge is open. Type craft hoe if you have iron, firewood, and one coin.")
        if world.content_version == APPRENTICESHIP_CONTENT_VERSION and sim.forge_open():
            mentor = world.actors[routes.BLACKSMITH]
            if player in world.hammer_training:
                lines.append("Hammer recipe available. Type craft hammer.")
            elif mentor.location == routes.FORGE and mentor.alive and mentor.can_work and not sim.is_busy(routes.BLACKSMITH):
                lines.append("Ada is at the forge. Type learn hammer to take a lesson.")
    return "\n".join(lines)


def inventory(sim: Simulation) -> str:
    world = sim.world
    player = character(sim)
    actor = world.actors[player]
    settings = world.config.village
    goods = ", ".join(f"{good}: {quantity}" for good, quantity in sorted(world.inventory[player].items()))
    lines = [f"Inventory: {goods}"]
    for records in (world.crafted_hoes, world.crafted_hammers):
        for key, tool in sorted(records.items()):
            if tool.account == player:
                lines.append(f"{key}: quality {tool.quality}/100, {tool.uses_left} uses left")
    hunger = village.hunger_at(actor, world.minute, settings)
    lines.append(f"Hunger: {hunger} / {settings.meal_relief * 3}. Fatigue: {actor.fatigue} / {settings.fatigue_limit}.")
    return "\n".join(lines)


def grain_offers(sim: Simulation, player: str) -> list[market.GrainOffer]:
    actor = sim.world.actors[player]
    trip = sim.active.get(player)
    if actor.location != routes.MARKET_SQUARE or (trip and isinstance(trip.intent, Travel)):
        raise WorldError("visit market-square to see offers or buy grain")
    return market.offers(sim.world, sim.available)


def skills(sim: Simulation) -> str:
    player = character(sim)
    if sim.world.content_version not in CIVILIAN_CONTENT_VERSIONS:
        return "Blacksmithing progression is available in the civilian scenario."
    xp = sim.world.blacksmithing_xp.get(player, 0)
    result = f"Blacksmithing: rank {blacksmith.skill_rank(xp)}, {xp} XP."
    if sim.world.content_version == APPRENTICESHIP_CONTENT_VERSION:
        hammer = ", hammer" if player in sim.world.hammer_training else ""
        result += f"\nRecipes: hoe{hammer}."
    return result


def market_view(sim: Simulation) -> str:
    offers = grain_offers(sim, character(sim))
    lines = [f"{offer.seller}: {offer.quantity} grain at {offer.price} coin each" for offer in offers]
    if sim.world.content_version in CIVILIAN_CONTENT_VERSIONS:
        for seller, good, price in (
            (routes.SMELTER, IRON, blacksmith.IRON_PRICE),
            (routes.WOODCUTTER, FIREWOOD, forestry.FIREWOOD_PRICE),
        ):
            quantity = sim.available(routes.stall(seller), good)
            if quantity and sim.world.actors[seller].alive:
                lines.append(f"{seller}: {quantity} {good} at {price} coin each")
        if (blacksmith.accepts_tools(sim.world, sim.available)
                and sim.available(routes.BLACKSMITH, COIN) >= blacksmith.HOE_BUYBACK):
            lines.append(f"Ada buys hoes for {blacksmith.HOE_BUYBACK} coin each.")
    return "\n".join(lines) or "Nothing is currently offered at the market."


def orders_view(sim: Simulation) -> str:
    world = sim.world
    player = character(sim)
    if world.content_version not in CONTRACTS_CONTENT_VERSIONS:
        raise WorldError("hoe orders require the contracts scenario")
    active = sim.active.get(player)
    if world.actors[player].location != routes.MARKET_SQUARE or (active and isinstance(active.intent, Travel)):
        raise WorldError("visit market-square to read the hoe orders")
    lines = []
    for key, order in sorted(world.hoe_orders.items(), key=lambda pair: (pair[1].deadline, pair[0])):
        if order.status in contracts.OPEN_STATUSES:
            assignee = world.actors[order.supplier].name if order.supplier else "open"
            lines.append(f"{key} | {order.farm} | {contracts.PRICE} coin | quality {contracts.MIN_QUALITY}+"
                         f" | due before minute {order.deadline} | {assignee}")
    return "\n".join(lines) or "There are no active hoe orders."


def act(sim: Simulation, command: str, argument: str) -> str:
    world = sim.world
    player = character(sim)
    location = world.actors[player].location
    settings = world.config.village
    match command:
        case "go":
            if argument == location:
                raise WorldError("you are already at that location")
            if argument != routes.MARKET_SQUARE and argument not in routes.roads_for(world):
                raise WorldError("unknown location. Type look to see the roads from here")
            duration = routes.distance(world, location, argument)
            intent = Travel(player, location, argument, duration)
            message = f"Arrived at {argument} after {duration} minutes."
        case "buy":
            if world.content_version in CIVILIAN_CONTENT_VERSIONS and argument == IRON:
                intent = ForgeIntent("buy_iron", player, settings.purchase_minutes, blacksmith.IRON_PRICE)
                message = f"Bought one iron bar for {blacksmith.IRON_PRICE} coin."
            elif world.content_version in CIVILIAN_CONTENT_VERSIONS and argument == FIREWOOD:
                intent = FirewoodIntent("buy_firewood", player, settings.purchase_minutes, price=forestry.FIREWOOD_PRICE)
                message = f"Bought one firewood bundle for {forestry.FIREWOOD_PRICE} coin."
            else:
                offer = next((offer for offer in grain_offers(sim, player)
                              if not argument or offer.seller == argument), None)
                if offer is None:
                    raise WorldError("no grain is currently offered by that seller" if argument else "no grain is for sale")
                intent = MarketIntent("buy_food", player, settings.purchase_minutes, offer.seller, offer.price)
                message = f"Bought one grain from {offer.seller} for {offer.price} coin."
        case "work":
            if location == routes.FORGE and world.content_version in CIVILIAN_CONTENT_VERSIONS:
                intent = ForgeIntent("forge_hoe", player, blacksmith.FORGE_MINUTES)
                message = f"Forged one hoe for Ada. Earned {settings.wage} coin and 1 blacksmithing XP."
            else:
                farm = next((owner for owner, field in routes.fields_for(world).items() if field == location), None)
                if farm is None:
                    raise WorldError("visit a farm to take a paid harvest shift")
                intent = farm_tools.harvest(world, player, settings.harvest_minutes, farm, sim.hoe_is_free)
                message = f"Finished the harvest shift. Earned {settings.wage} coin."
        case "craft":
            kind = f"forge_{argument}"
            if world.content_version not in CIVILIAN_CONTENT_VERSIONS or kind not in blacksmith.FORGE_RECIPES:
                raise WorldError("use craft hoe or craft hammer in a career scenario")
            intent = PersonalForge(kind, player, blacksmith.FORGE_RECIPES[kind][1])
            message = (f"Forged a {argument} with your materials. "
                       f"Paid {blacksmith.FORGE_RENT} coin rent and earned 1 XP.")
        case "learn":
            if argument != "hammer":
                raise WorldError("use learn hammer at the apprenticeship forge")
            intent = ForgeIntent("learn_hammer", player, blacksmith.HAMMER_LESSON_MINUTES)
            message = f"Learned the hammer recipe from Ada for {blacksmith.HAMMER_LESSON_PRICE} coin."
        case "sell":
            if world.content_version not in CIVILIAN_CONTENT_VERSIONS or argument != "hoe":
                raise WorldError("use sell hoe in the civilian scenario")
            intent = ForgeIntent("sell_hoe", player, settings.purchase_minutes, blacksmith.HOE_BUYBACK)
            message = f"Sold one hoe to Ada for {blacksmith.HOE_BUYBACK} coin."
        case "accept":
            intent = OrderIntent("accept_order", player, order_id=argument)
            message = f"Accepted {argument}."
        case "deliver":
            intent = OrderIntent("deliver_order", player, order_id=argument,
                                 item_id=contracts.eligible_item(world, player))
            message = f"Delivered {argument} and received {contracts.PRICE} coin."
        case "eat":
            intent = VillageIntent("eat", player, settings.eat_minutes)
            message = "Ate one grain."
        case "rest":
            intent = VillageIntent("rest", player, settings.rest_minutes)
            message = f"Rested for {settings.rest_minutes} minutes."
        case "wait":
            try:
                minutes = int(argument)
            except ValueError:
                raise WorldError("wait takes a whole number of minutes") from None
            integer("wait minutes", minutes, 1, world.config.minutes_per_day)
            sim.record("player_waited", {"actor": player, "minutes": minutes})
            sim.advance_to(world.minute + minutes)
            return f"Waited {minutes} minutes."
        case _:
            raise WorldError("unknown action")
    cause = sim.record("player_command", {"actor": player, "command": command})
    action = sim.submit(f"{PLAYER_ACTION_PREFIX}{cause}", intent, cause_id=cause)
    sim.advance_to(action.finishes_at)
    if action.status == "failed" or (isinstance(intent, ForgeIntent) and intent.kind in blacksmith.FORGE_RECIPES):
        outcome = next(event for event in reversed(sim.events) if event.id == action.outcome_event)
        if action.status == "failed":
            return f"Action failed. {outcome.payload['reason']}"
        good, _ = blacksmith.FORGE_RECIPES[intent.kind]
        item = outcome.payload[craftsmanship.TOOL_FIELDS[good]][0]
        label = intent.kind.removeprefix("forge_").capitalize()
        message += f" {label} {item['id']} quality {item['quality']}/100."
        if "hammer_used" in outcome.payload:
            message += f" Your hammer added {outcome.payload['hammer_quality_bonus']} quality."
    return message


def execute(save: Save, line: str) -> str:
    words = line.lower().split()
    if not words:
        return ""
    word, *args = words
    limits = COMMAND_ARGUMENTS.get(word)
    if limits is None:
        raise WorldError("unknown command. Type help to see the available commands")
    if not limits[0] <= len(args) <= limits[1]:
        raise WorldError(f"invalid arguments for {word}. Type help for command usage")
    if word == "look":
        return save.read(look)
    if word == "inventory":
        return save.read(inventory)
    if word == "skills":
        return save.read(skills)
    if word == "market":
        return save.read(market_view)
    if word == "orders":
        return save.read(orders_view)
    argument = args[0] if args else ""
    return save.mutate(lambda sim: act(sim, word, argument))


def play(save: Save) -> None:
    print(save.read(look))
    print("Type help for commands or quit to close.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if line.lower() == "quit":
            return
        if line.lower() == "help":
            print(HELP)
        elif line:
            try:
                print(execute(save, line))
            except WorldError as error:
                print(error)
