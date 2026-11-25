import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from living_world import contracts
from living_world.model import COIN, FARM_OWNER, IRON_HOE, Config, CraftedHoe, OrderIntent, ToolIntent, WorldError
from living_world.persistence import Save
from living_world.player import execute
from living_world.routes import BLACKSMITH, MARKET_SQUARE, WEST_FARM, stall


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def create(self, case, *, player=True, config=None, scenario="contracts"):
        return Save.create(self.directory / f"{case}.db", 8, config, scenario=scenario,
                           player_name="Iara" if player else None)

    def commission(self, save, *, short_waits):
        execute(save, "go market-square")
        waits = ["wait 12"] * 67 if short_waits else ["wait 804"]
        for command in waits:
            execute(save, command)
        key, order = save.read(lambda sim: next(iter(sim.world.hoe_orders.items())))
        self.assertEqual(order.farm, WEST_FARM)
        self.assertIn(f"{key} | {WEST_FARM} | 19 coin | quality 40+", execute(save, "orders"))
        self.assertEqual(save.summary()["village"]["orders"]["coin_in_escrow"], 19)
        execute(save, f"accept {key}")
        return key, order

    def make_hoe(self, save, *, short_waits):
        wait_two = ["wait 60"] * 2 if short_waits else ["wait 120"]
        wait_five = ["wait 60"] * 5 if short_waits else ["wait 300"]
        for command in (
            "go east-farm", *wait_two, "work", "work", "rest", "work", *wait_two, "work", "rest",
            *wait_five, "work", "work", "rest", "go market-square", "buy iron", "buy firewood",
            "go forge", "craft hoe", "go market-square",
        ):
            execute(save, command)

    def test_player_delivers_the_qualified_tool_and_receives_the_reserved_payment(self):
        save = self.create("delivered")
        key, order = self.commission(save, short_waits=True)
        self.make_hoe(save, short_waits=True)
        item = save.read(lambda sim: contracts.eligible_item(sim.world, "player"))
        self.assertIsNotNone(item)
        save.submit("delivery", OrderIntent("deliver_order", "player", order_id=key, item_id=item))
        save = Save(save.path)
        save.advance(minutes=1)

        report = save.inspect(journal=True)
        completed = report["snapshot"]["hoe_orders"][key]
        self.assertEqual(completed["status"], "delivered")
        self.assertEqual(completed["supplier"], "player")
        self.assertEqual(completed["item_id"], item)
        self.assertEqual(report["snapshot"]["crafted_hoes"][item]["account"], stall(order.farm))
        self.assertEqual(report["snapshot"]["inventory"]["player"][COIN], 19)
        self.assertEqual(report["snapshot"]["inventory"][contracts.escrow(order.farm)][COIN], 0)
        with self.assertRaisesRegex(WorldError, "closed"):
            execute(save, f"deliver {key}")
        save.audit_inventory()

    def test_low_quality_is_rejected_and_missed_order_refunds_the_farm(self):
        save = self.create("expired")
        key, order = self.commission(save, short_waits=False)
        self.make_hoe(save, short_waits=False)
        self.assertIn("quality 32/100", execute(save, "inventory"))
        before = save.inspect(journal=True)
        with self.assertRaisesRegex(WorldError, "quality 40"):
            execute(save, f"deliver {key}")
        self.assertEqual(save.inspect(journal=True), before)

        save.advance_to(order.deadline - 1)
        self.assertEqual(save.summary()["village"]["orders"]["coin_in_escrow"], 19)
        Save(save.path).advance_to(order.deadline)
        with self.assertRaisesRegex(WorldError, "closed"):
            execute(save, f"deliver {key}")
        report = save.inspect(journal=True)
        self.assertEqual(report["snapshot"]["hoe_orders"][key]["status"], "expired")
        self.assertEqual(report["snapshot"]["inventory"][contracts.escrow(order.farm)][COIN], 0)
        expired = next(event for event in report["journal"]
                       if event["kind"] == "order_expired" and event["payload"]["order_id"] == key)
        self.assertEqual(expired["cause_id"], order.funding_event)
        self.assertEqual(expired["payload"]["movements"], [
            {"source": contracts.escrow(order.farm), "destination": order.farm, "good": COIN, "quantity": 19},
        ])
        save.audit_inventory()

    def test_ada_can_win_and_fill_the_same_market_offer(self):
        idle = self.create("idle")
        control = self.create("control", player=False)
        for save in (idle, control):
            save.advance_to(1400)
        for save in (idle, control):
            orders = save.inspect()["snapshot"]["hoe_orders"]
            winner = next(order for order in orders.values() if order["farm"] == WEST_FARM)
            self.assertEqual(winner["supplier"], BLACKSMITH)
            self.assertEqual(winner["status"], "delivered")
            self.assertEqual(save.summary()["village"]["orders"]["collected"], 1)
            save.audit_inventory()

    def test_posting_needs_real_funds_and_competing_acceptances_are_serialized(self):
        for coins in (18, 19):
            with self.subTest(coins=coins):
                config = Config.from_mapping({"village": {"starting_owner_coin": coins}})
                save = self.create(f"race-{coins}", config=config)

                def stage(sim):
                    sim.world.queue.clear()
                    for actor in (FARM_OWNER, "player", BLACKSMITH):
                        current = sim.world.actors[actor]
                        sim.world.actors[actor] = replace(current, location=MARKET_SQUARE)

                save.mutate(stage)
                posting = OrderIntent("post_order", FARM_OWNER)
                if coins == 18:
                    with self.assertRaisesRegex(WorldError, "insufficient available coin"):
                        save.submit("post", posting)
                    continue
                save.submit("post", posting)
                save.advance(minutes=1)
                key = save.read(lambda sim: next(iter(sim.world.hoe_orders)))
                save.submit("first", OrderIntent("accept_order", BLACKSMITH, order_id=key))
                with self.assertRaisesRegex(WorldError, "another supplier"):
                    save.submit("second", OrderIntent("accept_order", "player", order_id=key))
                Save(save.path).advance(minutes=1)
                self.assertEqual(save.inspect()["snapshot"]["hoe_orders"][key]["supplier"], BLACKSMITH)
                save.audit_inventory()

    def test_ordinary_purchase_cannot_take_the_hoe_reserved_for_delivery(self):
        config = Config.from_mapping({"village": {"starting_owner_coin": 30}})
        save = self.create("item-race", config=config)

        def place_at_market(sim):
            sim.world.queue.clear()
            for actor in (WEST_FARM, FARM_OWNER, BLACKSMITH):
                current = sim.world.actors[actor]
                sim.world.actors[actor] = replace(current, location=MARKET_SQUARE)

        save.mutate(place_at_market)
        save.submit("post", OrderIntent("post_order", WEST_FARM))
        save.advance_to(1)
        key = save.read(lambda sim: next(iter(sim.world.hoe_orders)))
        save.submit("accept", OrderIntent("accept_order", BLACKSMITH, order_id=key))
        save.advance_to(2)

        shop = stall(BLACKSMITH)

        def stock_stall(sim):
            sim.world.queue[:] = [event for event in sim.world.queue if event.kind != "decide"]
            sim.world.inventory[shop][IRON_HOE] = 2
            sim.world.crafted_hoes["hoe-11"] = CraftedHoe(BLACKSMITH, shop, 55, 8, "stock", "stock", 2)
            sim.world.crafted_hoes["hoe-12"] = CraftedHoe(BLACKSMITH, shop, 35, 8, "stock", "stock", 2)

        save.mutate(stock_stall)
        save.submit("buy", ToolIntent("buy_hoe", FARM_OWNER, 8, price=18))
        save.advance_to(9)
        save.submit("deliver", OrderIntent("deliver_order", BLACKSMITH, order_id=key, item_id="hoe-11"))
        save.advance_to(10)
        state = save.inspect()["snapshot"]
        self.assertEqual(state["crafted_hoes"]["hoe-11"]["account"], stall(WEST_FARM))
        self.assertEqual(state["crafted_hoes"]["hoe-12"]["account"], FARM_OWNER)

    def test_matched_career_run_changes_who_supplies_the_farm_and_gets_paid(self):
        active = self.create("active-career", scenario="apprenticeship")
        idle = self.create("idle-career", scenario="apprenticeship")
        self.assertEqual(active.inspect(journal=True), idle.inspect(journal=True))
        key, order = self.commission(active, short_waits=True)
        self.make_hoe(active, short_waits=True)
        execute(active, f"deliver {key}")
        for command in ("wait 9", "buy", "eat"):
            execute(active, command)

        for save, supplier, player_coins in ((active, "player", 18), (idle, BLACKSMITH, 3)):
            save.advance_to(7 * Config().minutes_per_day)
            report = save.inspect(journal=True)
            settlement = next(event for event in report["journal"]
                              if event["kind"] == "deliver_order_completed"
                              and event["payload"]["order"]["farm"] == order.farm)
            item = settlement["payload"]["order"]["item_id"]
            self.assertEqual(settlement["payload"]["actor"], supplier)
            self.assertEqual(settlement["payload"]["movements"][-1], {
                "source": contracts.escrow(order.farm), "destination": supplier, "good": COIN, "quantity": 19,
            })
            self.assertTrue(any(event["kind"] == "harvest_completed"
                                and event["payload"].get("hoe_used") == item for event in report["journal"]))
            self.assertEqual(report["snapshot"]["inventory"]["player"][COIN], player_coins)
            self.assertEqual(save.summary()["village"]["coin_supply"], 225)
            save.audit_inventory()
