"""Discrete-event rules. This module has no I/O or wall-clock dependencies."""

from __future__ import annotations

import re
from dataclasses import asdict, replace
from heapq import heapify, heappop, heappush
from random import Random

from . import blacksmith, contracts, craftsmanship, farm_tools, forestry, kiln, market, mining, routes, seed_trade, smelting, village
from .model import (
    ANVIL, APPRENTICESHIP_CONTENT_VERSION, CIVILIAN_CONTENT_VERSION, CIVILIAN_CONTENT_VERSIONS, COIN,
    CONTRACTS_CONTENT_VERSION, CONTRACTS_CONTENT_VERSIONS, FARM_OWNER, FIREWOOD, GRAIN, IRON,
    IRON_HAMMER, IRON_HOE, MARKET_CONTENT_VERSION,
    MARKET_CONTENT_VERSIONS, MAX_CLOCK, MAX_QUANTITY,
    HAMLET_CONTENT_VERSION, HAMLET_CONTENT_VERSIONS, SEED_GRAIN, SEED_SAVING_CONTENT_VERSION,
    SEED_TRADE_CONTENT_VERSION, SPATIAL_CONTENT_VERSIONS, VILLAGE_CONTENT_VERSIONS, WORKSHOP_CONTENT_VERSIONS,
    Action, Actor, CharcoalIntent,
    Config, Event, FirewoodIntent, ForgeIntent, HoeHarvest, Intent, MarketIntent, MiningIntent,
    Movement, OrderIntent, Scheduled, SeedIntent, SmeltingIntent, ToolIntent, Transfer, Travel, VillageIntent,
    World, WorldError, integer,
)

COMPLETION_PRIORITY = 0
DECISION_PRIORITY = 1
NPC_ACTION_PREFIX = "npc-"
PLAYER_ACTION_PREFIX = "player-"
PLAYER_ID = "player"


class Simulation:
    def __init__(self, world: World) -> None:
        self.world = world
        heapify(world.queue)
        self.events: list[Event] = []
        self.active = {action.intent.actor: action for action in world.actions.values()
                       if action.status == "started"}
        self.random = Random(0)
        self.random.setstate(world.rng_state)

    @classmethod
    def create(
        cls, seed: int, config: Config, scenario: str = "lab", *, player_name: str | None = None,
    ) -> Simulation:
        integer("seed", seed, -MAX_CLOCK - 1, MAX_CLOCK)
        rng = Random(f"living-world:generation:{seed}")
        apprenticeship = scenario == "apprenticeship"
        with_orders = apprenticeship or scenario == "contracts"
        civilian = with_orders or scenario == "civilian"
        hamlet = civilian or scenario == "hamlet"
        if player_name is not None:
            if not hamlet:
                raise WorldError("a player character requires the hamlet or civilian scenarios")
            player_name = player_name.strip()
            if not 1 <= len(player_name) <= 32 or not player_name.isprintable():
                raise WorldError("a character name needs 1 to 32 printable characters")
        with_seed_trade = hamlet or scenario == "seed-trade"
        if with_seed_trade:
            scenario = "seed-saving"
        if scenario == "lab":
            grain = rng.randint(config.starting_grain_min, config.starting_grain_max)
            world = World(
                seed=seed,
                config=config,
                rng_state=rng.getstate(),
                actors={
                    "storekeeper": Actor("Marra", "granary"),
                    "neighbor": Actor("Iven", "granary"),
                },
                inventory={"storekeeper": {GRAIN: grain},
                           "neighbor": {GRAIN: config.neighbor_starting_grain}},
            )
        elif scenario == "village":
            world = village.create_village(seed, config, rng)
        elif scenario in (
            "market", "routes", "firewood", "charcoal", "mining", "smelting", "blacksmith", "tools",
            "seed-saving",
        ):
            world = market.create_market(seed, config, rng, config.hamlet.farmhands if hamlet else None)
            if scenario != "market":
                routes.separate_sites(world)
            if scenario in ("firewood", "charcoal", "mining", "smelting", "blacksmith", "tools", "seed-saving"):
                forestry.add_woodland(world)
            if scenario in ("charcoal", "mining", "smelting", "blacksmith", "tools", "seed-saving"):
                kiln.add_kiln(world)
            if scenario in ("mining", "smelting", "blacksmith", "tools", "seed-saving"):
                mining.add_mine(world)
            if scenario in ("smelting", "blacksmith", "tools", "seed-saving"):
                smelting.add_smeltery(world)
            if scenario in ("blacksmith", "tools", "seed-saving"):
                blacksmith.add_forge(world)
            if scenario in ("tools", "seed-saving"):
                farm_tools.enable_tools(world)
            if scenario == "seed-saving":
                world.content_version = SEED_TRADE_CONTENT_VERSION if with_seed_trade else SEED_SAVING_CONTENT_VERSION
                if hamlet:
                    world.content_version = CIVILIAN_CONTENT_VERSION if civilian else HAMLET_CONTENT_VERSION
                    world.inventory[blacksmith.FORGE_INPUTS] = {IRON: 0}
                    routes.add_hamlet_farms(world)
                    if civilian:
                        world.blacksmithing_xp[routes.BLACKSMITH] = blacksmith.EXPERIENCED_XP
                        world.inventory[blacksmith.FORGE_INPUTS].update({ANVIL: 1, FIREWOOD: 0})
                    if with_orders:
                        world.content_version = APPRENTICESHIP_CONTENT_VERSION if apprenticeship else CONTRACTS_CONTENT_VERSION
                        for farm in routes.fields_for(world):
                            world.inventory[contracts.escrow(farm)] = {COIN: 0}
        else:
            raise WorldError(f"unknown scenario {scenario!r}")
        if player_name is not None:
            world.player_id = PLAYER_ID
            world.actors[PLAYER_ID] = Actor(player_name, routes.FIELDS[FARM_OWNER])
            world.inventory[PLAYER_ID] = {COIN: config.village.starting_hand_coin, GRAIN: 0}
        sim = cls(world)
        initialized = sim.record("world_initialized", {
            "inventory": {actor: stock.copy() for actor, stock in world.inventory.items()},
        })
        if world.content_version in VILLAGE_CONTENT_VERSIONS:
            for actor in sorted(world.actors):
                if actor != world.player_id:
                    sim.wake(actor, rng.randint(1, 30), initialized)
        return sim

    def record(
        self, kind: str, payload: dict[str, object], cause_id: int | None = None,
    ) -> int:
        event_id = self.world.next_event_id
        self.events.append(Event(event_id, self.world.minute, kind, payload, cause_id))
        self.world.next_event_id += 1
        return event_id

    def enqueue(self, event: Scheduled) -> None:
        integer("scheduled minute", event.minute, self.world.minute + 1, MAX_CLOCK)
        heappush(self.world.queue, event)
        self.world.next_sequence += 1

    def schedule(self, minute: int, priority: int, action_id: str) -> None:
        self.enqueue(Scheduled(minute, priority, self.world.next_sequence, action_id))

    def wake(self, actor: str, delay: int, cause_id: int) -> None:
        if (actor == self.world.player_id or self.world.content_version not in VILLAGE_CONTENT_VERSIONS
                or self.world.minute == MAX_CLOCK):
            return
        if any(event.kind == "decide" and event.subject == actor for event in self.world.queue):
            return
        minute = min(self.world.minute + delay, MAX_CLOCK)
        self.enqueue(Scheduled(minute, DECISION_PRIORITY, self.world.next_sequence,
                               actor, "decide", cause_id))

    def movements(self, intent: Intent, *, harvested: int = 0) -> tuple[Movement, ...]:
        if isinstance(intent, Transfer):
            return (Movement(intent.actor, intent.target, intent.good, intent.quantity),)
        if isinstance(intent, Travel):
            return routes.movements(intent)
        if isinstance(intent, FirewoodIntent):
            return forestry.movements(intent)
        if isinstance(intent, CharcoalIntent):
            return kiln.movements(intent)
        if isinstance(intent, MiningIntent):
            return mining.movements(intent)
        if isinstance(intent, SmeltingIntent):
            return smelting.movements(intent)
        if isinstance(intent, ForgeIntent):
            return blacksmith.movements(self.world, intent)
        if isinstance(intent, ToolIntent):
            return farm_tools.movements(intent)
        if isinstance(intent, SeedIntent):
            return seed_trade.movements(intent)
        if isinstance(intent, OrderIntent):
            return contracts.movements(self.world, intent)
        return village.activity_movements(intent, self.world, harvested=harvested)

    def available(self, owner: str, good: str) -> int:
        reserved = sum(
            move.quantity for action in self.active.values() for move in self.movements(action.intent)
            if move.source == owner and move.good == good
        )
        return self.world.inventory[owner].get(good, 0) - reserved

    def submit(self, key: str, intent: Intent, *, cause_id: int | None = None) -> Action:
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key):
            raise WorldError("action id must have 1 to 64 letters, digits, underscores or hyphens")
        if cause_id is None and key.startswith(NPC_ACTION_PREFIX):
            raise WorldError(f"action ids starting with {NPC_ACTION_PREFIX!r} are reserved")
        if self.world.player_id is not None and cause_id is None and key.startswith(PLAYER_ACTION_PREFIX):
            raise WorldError(f"action ids starting with {PLAYER_ACTION_PREFIX!r} are reserved")
        if isinstance(intent, Transfer):
            integer("quantity", intent.quantity, 1, MAX_QUANTITY)
        integer("duration", intent.duration, 1, self.world.config.max_action_minutes)
        existing = self.world.actions.get(key)
        if existing is not None:
            if existing.intent != intent:
                raise WorldError(f"action id {key!r} already belongs to a different intent")
            return existing
        self.validate(intent)
        if self.is_busy(intent.actor):
            raise WorldError(f"actor {intent.actor!r} is already busy")
        if isinstance(intent, MarketIntent):
            self.validate_market_start(intent)
        if isinstance(intent, ForgeIntent):
            if (self.world.content_version in WORKSHOP_CONTENT_VERSIONS
                    and intent.kind in blacksmith.WORKSHOP_ACTIVITIES and not self.forge_open()):
                raise WorldError("the forge shift is occupied")
            if intent.kind == "learn_hammer" and self.is_busy(routes.BLACKSMITH):
                raise WorldError("Ada is busy")
        if isinstance(intent, ForgeIntent) and intent.kind == "sell_hoe":
            if not blacksmith.accepts_tools(self.world, self.available):
                raise WorldError("Ada is stocked and has no open offer for a hoe")
        if isinstance(intent, SeedIntent) and intent.kind == "buy_seed":
            assert intent.seller is not None
            if not seed_trade.has_surplus(self.world, intent.seller, self.available):
                raise WorldError(f"no surplus seed offered by {intent.seller}")
        if isinstance(intent, OrderIntent):
            self.validate_order_start(intent)
        reservations = [move for move in self.movements(intent) if move.source is not None]
        for move in reservations:
            if self.available(move.source, move.good) < move.quantity:
                raise WorldError(f"insufficient available {move.good} for {move.source}")
        finishes = self.world.minute + intent.duration
        self.schedule(finishes, COMPLETION_PRIORITY, key)
        activity = "transfer" if isinstance(intent, Transfer) else intent.kind
        event = self.record("action_started", {
            "action": key, "type": activity, "intent": asdict(intent), "finishes_at": finishes,
            "reservations": [asdict(move) for move in reservations],
        }, cause_id)
        action = Action(intent, self.world.minute, finishes, event)
        self.world.actions[key] = action
        self.active[intent.actor] = action
        return action

    def validate(self, intent: Intent) -> None:
        if not isinstance(intent.actor, str):
            raise WorldError("actor must be an actor ID")
        actor = self.world.actors.get(intent.actor)
        if actor is None:
            raise WorldError(f"unknown actor {intent.actor!r}")
        if not actor.alive:
            raise WorldError(f"actor {intent.actor!r} must be alive")
        if isinstance(intent, Travel):
            routes.validate_travel(self.world, intent)
            return
        if isinstance(intent, FirewoodIntent):
            forestry.validate(self.world, intent)
            return
        if isinstance(intent, CharcoalIntent):
            kiln.validate(self.world, intent)
            return
        if isinstance(intent, MiningIntent):
            mining.validate(self.world, intent)
            return
        if isinstance(intent, SmeltingIntent):
            smelting.validate(self.world, intent)
            return
        if isinstance(intent, ForgeIntent):
            blacksmith.validate(self.world, intent)
            return
        if isinstance(intent, ToolIntent):
            farm_tools.validate(self.world, intent)
            return
        if isinstance(intent, SeedIntent):
            seed_trade.validate(self.world, intent)
            return
        if isinstance(intent, OrderIntent):
            contracts.validate(self.world, intent)
            return
        if isinstance(intent, (VillageIntent, MarketIntent)):
            village.validate_activity(self.world, intent)
            if isinstance(intent, MarketIntent):
                market.validate_activity(self.world, intent)
            if isinstance(intent, HoeHarvest):
                farm_tools.validate_harvest(self.world, intent)
            return
        if not isinstance(intent.target, str):
            raise WorldError("target must be an actor ID")
        if intent.good != GRAIN:
            raise WorldError(f"unknown good {intent.good!r}")
        target = self.world.actors.get(intent.target)
        if target is None:
            raise WorldError(f"unknown target {intent.target!r}")
        if intent.actor == intent.target:
            raise WorldError("a transfer needs a different recipient")
        if not target.alive:
            raise WorldError(f"target {intent.target!r} must be alive")
        target_action = self.active.get(intent.target)
        if target_action and isinstance(target_action.intent, Travel):
            raise WorldError(f"target {intent.target!r} is traveling")
        if actor.location != target.location:
            raise WorldError("both actors must be in the same location")

    def validate_market_start(self, intent: MarketIntent) -> None:
        if isinstance(intent, HoeHarvest) and not self.hoe_is_free(intent.farm):
            raise WorldError(f"the hoe at {intent.farm} is already reserved")
        if intent.kind == "buy_food":
            offer = next((offer for offer in market.offers(self.world, self.available)
                          if offer.seller == intent.farm), None)
            if offer is None:
                raise WorldError(f"no grain offered by {intent.farm}")
            if offer.price != intent.price:
                raise WorldError(f"price changed to {offer.price} coin for {intent.farm}")
        elif intent.kind == "harvest" and intent.actor != intent.farm and not self.hired_shift_open(intent.farm):
            raise WorldError(f"the hired field shift is occupied at {intent.farm}")

    def reserved_order_items(self) -> frozenset[str]:
        return frozenset(
            action.intent.item_id for action in self.active.values()
            if isinstance(action.intent, OrderIntent) and action.intent.item_id is not None
        )

    def validate_order_start(self, intent: OrderIntent) -> None:
        if intent.kind == "post_order":
            if self.available(routes.stall(routes.BLACKSMITH), IRON_HOE):
                raise WorldError("the blacksmith stall already has a hoe for sale")
            if self.world.minute + intent.duration + 2 * self.world.config.minutes_per_day > MAX_CLOCK:
                raise WorldError("the order deadline would exceed the simulation clock")
            return
        if intent.order_id is None:
            return
        order = self.world.hoe_orders[intent.order_id]
        if self.world.minute + intent.duration >= order.deadline:
            raise WorldError("the hoe order closes before this action can finish")
        if intent.kind == "accept_order" and any(
            isinstance(action.intent, OrderIntent) and action.intent.kind == "accept_order"
            and action.intent.order_id == intent.order_id for action in self.active.values()
        ):
            raise WorldError("another supplier is accepting this order")
        if intent.item_id in self.reserved_order_items():
            raise WorldError("this hoe already has a pending delivery")

    def hired_shift_open(self, farm: str) -> bool:
        shifts = (self.world.config.hamlet.hired_shifts_per_farm
                  if self.world.content_version in HAMLET_CONTENT_VERSIONS else 1)
        return sum(
            isinstance(action.intent, MarketIntent) and action.intent.kind == "harvest"
            and action.intent.farm == farm and action.intent.actor != farm
            for action in self.active.values()
        ) < shifts

    def forge_open(self) -> bool:
        return not any(isinstance(action.intent, ForgeIntent) and action.intent.kind in blacksmith.WORKSHOP_ACTIVITIES
                       for action in self.active.values())

    def is_busy(self, actor: str) -> bool:
        return actor in self.active or (
            self.world.content_version == APPRENTICESHIP_CONTENT_VERSION and actor == routes.BLACKSMITH
            and any(isinstance(action.intent, ForgeIntent)
                                               and action.intent.kind == "learn_hammer"
                                               for action in self.active.values())
        )

    def wake_after_action(self, intent: Intent, cause: int) -> None:
        self.wake(intent.actor, 1, cause)
        if isinstance(intent, ForgeIntent) and intent.kind == "learn_hammer":
            self.wake(routes.BLACKSMITH, 1, cause)

    def forge_hire_inbound(self) -> bool:
        return any(
            worker.startswith("farmhand-") and isinstance(action.intent, Travel)
            and action.intent.destination == routes.FORGE
            for worker, action in self.active.items()
        )

    def hoe_is_free(self, farm: str) -> bool:
        return not any(isinstance(action.intent, HoeHarvest) and action.intent.farm == farm
                       for action in self.active.values())

    def cancel(self, key: str, *, cause_id: int | None = None) -> Action:
        action = self.world.actions.get(key)
        if action is None:
            raise WorldError(f"unknown action {key!r}")
        if action.status == "canceled":
            return action
        if action.status != "started":
            raise WorldError(f"cannot cancel an action that is {action.status}")
        self.world.queue[:] = [event for event in self.world.queue
                               if event.kind != "complete" or event.subject != key]
        heapify(self.world.queue)
        action.status = "canceled"
        action.outcome_event = self.record("action_canceled", {"action": key},
                                           action.start_event if cause_id is None else cause_id)
        del self.active[action.intent.actor]
        self.wake_after_action(action.intent, action.outcome_event)
        return action

    def complete(self, key: str) -> None:
        action = self.world.actions[key]
        intent = action.intent
        del self.active[intent.actor]
        try:
            self.validate(intent)
            for move in self.movements(intent):
                if move.source is not None and self.available(move.source, move.good) < move.quantity:
                    raise WorldError(f"reserved {move.good} is no longer present for {move.source}")
        except WorldError as error:
            action.status = "failed"
            action.outcome_event = self.record(
                "action_failed", {"action": key, "reason": str(error)}, action.start_event,
            )
        else:
            self.apply(key, action)
        assert action.outcome_event is not None
        self.wake_after_action(intent, action.outcome_event)

    def apply(self, key: str, action: Action) -> None:
        intent = action.intent
        harvested = 0
        if isinstance(intent, (VillageIntent, MarketIntent)) and intent.kind == "harvest":
            settings = self.world.config.village
            harvested = self.random.randint(settings.harvest_min, settings.harvest_max)
            self.world.rng_state = self.random.getstate()
        tool_details: dict[str, object] = {}
        if isinstance(intent, HoeHarvest):
            harvested += farm_tools.HOE_BONUS
        movements = self.movements(intent, harvested=harvested)
        if isinstance(intent, HoeHarvest):
            movements += farm_tools.wear(self.world, intent.farm)
            tool_details["hoe_bonus_grain"] = farm_tools.HOE_BONUS
            tool_details["hoe_uses_remaining"] = self.world.hoe_uses[intent.farm]
        if isinstance(intent, ToolIntent) and intent.kind == "install_hoe":
            self.world.hoe_uses[intent.actor] = farm_tools.HOE_LIFETIME
            tool_details["hoe_uses_remaining"] = farm_tools.HOE_LIFETIME
        if self.world.content_version in CIVILIAN_CONTENT_VERSIONS:
            made = None
            if isinstance(intent, ForgeIntent):
                if intent.kind == "learn_hammer":
                    self.world.hammer_training.append(intent.actor)
                    tool_details["learned_recipe"] = "hammer"
                elif intent.kind in blacksmith.FORGE_RECIPES:
                    bonus = 0
                    if hammer := craftsmanship.use_hammer(self.world, intent.actor):
                        item, uses_left, bonus = hammer
                        tool_details.update(hammer_used=item, hammer_uses_remaining=uses_left, hammer_quality_bonus=bonus)
                        if uses_left == 0:
                            movements += (Movement(intent.actor, None, IRON_HAMMER, 1),)
                    made = craftsmanship.make_tool(self.world, intent, action.start_event, bonus)
                    xp = self.world.blacksmithing_xp.get(intent.actor, 0) + 1
                    self.world.blacksmithing_xp[intent.actor] = xp
                    tool_details["blacksmithing_xp"] = xp
            if isinstance(intent, HoeHarvest):
                tool_details["hoe_used"] = craftsmanship.record_wear(self.world, intent.farm)
            selected = intent.item_id if isinstance(intent, OrderIntent) else None
            reserved = self.reserved_order_items() if self.world.content_version in CONTRACTS_CONTENT_VERSIONS else frozenset()
            tool_details.update(craftsmanship.update_inventory(
                self.world, movements, made, selected=selected, reserved=reserved,
            ))
        self.apply_movements(movements)
        if isinstance(intent, Travel):
            actor = self.world.actors[intent.actor]
            self.world.actors[intent.actor] = replace(actor, location=intent.destination)
        payload: dict[str, object] = {
            "action": key,
            "actor": intent.actor,
            "location": self.world.actors[intent.actor].location,
            "movements": [asdict(move) for move in movements],
            **tool_details,
        }
        kind = "goods_transferred"
        if isinstance(intent, Travel):
            kind = "travel_completed"
            payload.update(origin=intent.source, destination=intent.destination, duration=intent.duration)
        if isinstance(intent, (
            VillageIntent, MarketIntent, FirewoodIntent, CharcoalIntent, MiningIntent,
            SmeltingIntent, ForgeIntent, ToolIntent,
        )):
            kind = f"{intent.kind}_completed"
            payload["needs"] = village.update_needs(self.world, intent)
        if isinstance(intent, MarketIntent):
            payload["farm"] = intent.farm
            if intent.kind == "buy_food":
                payload["price"] = intent.price
        if isinstance(intent, SeedIntent):
            kind = f"{intent.kind}_completed"
            if intent.seller is not None:
                payload.update(seller=intent.seller, price=seed_trade.SEED_PRICE)
        if isinstance(intent, OrderIntent):
            kind = f"{intent.kind}_completed"
            if intent.kind != "collect_order":
                order_id, order = contracts.apply(self.world, intent)
                payload.update(order_id=order_id, order=asdict(order))
                if intent.kind == "post_order":
                    self.enqueue(Scheduled(order.deadline, COMPLETION_PRIORITY, self.world.next_sequence,
                                           order_id, "order_deadline", order.funding_event))
        action.status = "completed"
        action.outcome_event = self.record(kind, payload, action.start_event)

    def apply_movements(self, movements: tuple[Movement, ...]) -> None:
        for move in movements:
            if move.source is not None:
                self.world.inventory[move.source][move.good] -= move.quantity
            if move.destination is not None:
                inventory = self.world.inventory[move.destination]
                inventory[move.good] = inventory.get(move.good, 0) + move.quantity

    def expire_order(self, event: Scheduled) -> None:
        order = self.world.hoe_orders[event.subject]
        if order.status not in contracts.OPEN_STATUSES:
            return
        source = contracts.escrow(order.farm)
        if self.available(source, COIN) != contracts.PRICE:
            raise WorldError("the order escrow does not match its promised payment")
        refund = Movement(source, order.farm, COIN, contracts.PRICE)
        self.apply_movements((refund,))
        self.world.hoe_orders[event.subject] = replace(order, status="expired")
        self.record("order_expired", {
            "order_id": event.subject, "farm": order.farm, "supplier": order.supplier, "movements": [asdict(refund)],
        }, event.cause_id)

    def market_shock(self, shock: market.MarketShock) -> None:
        if self.world.content_version not in MARKET_CONTENT_VERSIONS:
            raise WorldError("market shocks require a market save")
        if shock == "seed-shortage":
            source = routes.pantry(FARM_OWNER) if self.world.content_version in SPATIAL_CONTENT_VERSIONS else FARM_OWNER
            available = self.available(source, SEED_GRAIN)
            if not available:
                raise WorldError("the primary farm has no unreserved seed to lose")
            move = Movement(source, None, SEED_GRAIN, available)
            self.apply_movements((move,))
            self.record("seed_shortage", {"farm": FARM_OWNER, "movements": [asdict(move)]})
        elif shock == "worker-loss":
            worker = "farmhand-1"
            actor = self.world.actors[worker]
            if not actor.can_work:
                raise WorldError(f"actor {worker!r} is already unavailable for field work")
            self.world.actors[worker] = replace(actor, can_work=False)
            cause = self.record("worker_sidelined", {"actor": worker})
            shift = self.active.get(worker)
            if shift and isinstance(shift.intent, (MarketIntent, ForgeIntent)) and shift.intent.kind in (
                "harvest", *blacksmith.FORGE_RECIPES,
            ):
                key = next(key for key, action in self.world.actions.items() if action is shift)
                self.cancel(key, cause_id=cause)
        else:
            raise WorldError(f"unknown market shock {shock!r}")

    def decide(self, event: Scheduled) -> None:
        actor = event.subject
        if self.is_busy(actor) or not self.world.actors[actor].alive:
            return
        settings = self.world.config.village
        rejected: dict[str, str] = {}
        if self.world.content_version in SPATIAL_CONTENT_VERSIONS:
            forge_jobs = self.world.content_version in WORKSHOP_CONTENT_VERSIONS
            options = market.route_choices(
                self.world, actor, self.available, self.hired_shift_open, self.hoe_is_free,
                forge_open=forge_jobs and self.forge_open(),
                forge_hire_inbound=forge_jobs and self.forge_hire_inbound(),
            )
        elif self.world.content_version == MARKET_CONTENT_VERSION:
            options = market.choices(self.world, actor, self.available)
        else:
            activities = village.choices(self.world, actor, self.available(actor, GRAIN),
                                         self.available(actor, COIN), self.available(FARM_OWNER, GRAIN))
            options = (VillageIntent(kind, actor, village.duration(kind, settings)) for kind in activities)
        for intent in options:
            try:
                self.submit(f"{NPC_ACTION_PREFIX}{event.sequence}", intent, cause_id=event.cause_id)
            except WorldError as error:
                name = f"{intent.kind}/{intent.farm}" if isinstance(intent, MarketIntent) else intent.kind
                rejected[name] = str(error)
            else:
                return
        wake_in = settings.retry_minutes
        next_wake = min(self.world.minute + wake_in, MAX_CLOCK)
        reason = "no current need for an activity"
        if rejected:
            reason = "prerequisites unavailable"
        elif (self.world.content_version in MARKET_CONTENT_VERSIONS
              and village.hunger_at(self.world.actors[actor], self.world.minute, settings)
              >= settings.meal_relief):
            reason = "hungry and no grain available to eat or buy"
        cause = self.record("decision_waited", {
            "actor": actor, "rejected": rejected,
            "reason": reason,
            "next_wake": next_wake if next_wake > self.world.minute else None,
        }, event.cause_id)
        self.wake(actor, wake_in, cause)

    def advance_to(self, minute: int) -> None:
        integer("target minute", minute, self.world.minute, MAX_CLOCK)
        processed = 0
        while self.world.queue and self.world.queue[0].minute <= minute:
            if processed >= self.world.config.max_events_per_advance:
                raise WorldError("event limit exceeded. Advance by a shorter interval")
            event = heappop(self.world.queue)
            self.world.minute = event.minute
            if event.kind == "complete":
                self.complete(event.subject)
            elif event.kind == "order_deadline":
                self.expire_order(event)
            else:
                self.decide(event)
            processed += 1
        self.world.minute = minute
