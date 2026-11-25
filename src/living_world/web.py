"""Loopback browser adapter for the existing player commands and SQLite save."""

from __future__ import annotations

import json
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from threading import Lock

from . import contracts, player, routes, village
from .model import (
    APPRENTICESHIP_CONTENT_VERSION, CIVILIAN_CONTENT_VERSIONS, COIN, CONTRACTS_CONTENT_VERSIONS,
    GRAIN, Travel, WorldError, integer,
)
from .persistence import Save
from .simulation import Simulation

ASSETS = {
    "/": ("index.html", "text/html"),
    "/style.css": ("style.css", "text/css"),
    "/game.js": ("game.js", "text/javascript"),
}
MAX_REQUEST_BYTES = 4096


def view(sim: Simulation) -> dict[str, object]:
    actor_id = player.character(sim)
    world = sim.world
    actor = world.actors[actor_id]
    settings = world.config.village
    pending = sim.active.get(actor_id)
    trip = pending.intent if pending and isinstance(pending.intent, Travel) else None
    at_market = not trip and actor.location == routes.MARKET_SQUARE
    roads = routes.roads_for(world)
    exits = {} if trip else roads if at_market else {routes.MARKET_SQUARE: roads[actor.location]}
    career = world.content_version in CIVILIAN_CONTENT_VERSIONS
    shop_orders = at_market and world.content_version in CONTRACTS_CONTENT_VERSIONS
    apprenticeship = world.content_version == APPRENTICESHIP_CONTENT_VERSION
    return {
        "name": actor.name,
        "minute": world.minute,
        "day": world.minute // world.config.minutes_per_day + 1,
        "location": actor.location,
        "destination": trip.destination if trip else None,
        "exits": [{"location": stop, "minutes": mins} for stop, mins in sorted(exits.items())],
        "needs": {
            "hunger": village.hunger_at(actor, world.minute, settings),
            "hunger_limit": settings.meal_relief * 3,
            "fatigue": actor.fatigue,
            "fatigue_limit": settings.fatigue_limit,
        },
        "coins": world.inventory[actor_id][COIN],
        "grain": world.inventory[actor_id][GRAIN],
        "inventory": player.inventory(sim),
        "skills": player.skills(sim) if career else None,
        "market": player.market_view(sim) if at_market else None,
        "career_market": bool(at_market and career),
        "orders": [
            {"id": key, "farm": order.farm, "price": contracts.PRICE, "quality": contracts.MIN_QUALITY,
             "deadline": order.deadline, "open": order.status == "open",
             "supplier": world.actors[order.supplier].name if order.supplier else None,
             "assigned_to_player": order.supplier == actor_id}
            for key, order in sorted(world.hoe_orders.items(), key=lambda pair: (pair[1].deadline, pair[0]))
            if order.status in contracts.OPEN_STATUSES
        ] if shop_orders else None,
        "at_forge": bool(not trip and career and actor.location == routes.FORGE),
        "can_try_work": bool(not trip and (actor.location in routes.fields_for(world).values()
                                         or (career and actor.location == routes.FORGE))),
        "apprenticeship": apprenticeship,
        "knows_hammer": actor_id in world.hammer_training,
        "wait_minutes": min(60, world.config.minutes_per_day),
    }


class GameServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, save: Save, port: int = 8765) -> None:
        integer("port", port, 0, 65535)
        save.read(player.character)
        self.save = save
        self.command_lock = Lock()
        super().__init__(("127.0.0.1", port), GameHandler)
        self.authority = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.authority}"


class GameHandler(BaseHTTPRequestHandler):
    server: GameServer
    timeout = 10

    def log_message(self, format: str, *args: object) -> None:
        pass

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status: int, payload: dict[str, object]) -> None:
        self.respond(status, json.dumps(payload).encode("utf-8"), "application/json")

    def allowed_host(self) -> bool:
        if self.headers.get("Host") == self.server.authority:
            return True
        self.json(403, {"error": f"Abra o jogo em {self.server.origin}."})
        return False

    def do_GET(self) -> None:
        if not self.allowed_host():
            return
        if self.path in ASSETS:
            filename, content_type = ASSETS[self.path]
            asset = files("living_world").joinpath("web_assets", filename).read_bytes()
            self.respond(200, asset, content_type)
        elif self.path == "/api/state":
            try:
                self.json(200, self.server.save.read(view))
            except (WorldError, sqlite3.Error, OSError) as error:
                self.json(400, {"error": str(error)})
        else:
            self.json(404, {"error": "Página desconhecida."})

    def do_POST(self) -> None:
        if not self.allowed_host():
            return
        if self.path != "/api/command":
            self.json(404, {"error": "Comando desconhecido."})
            return
        if self.headers.get("Origin") != self.server.origin:
            self.json(403, {"error": "Envie comandos a partir da página do jogo."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_REQUEST_BYTES or self.headers.get_content_type() != "application/json":
                raise ValueError
            request = json.loads(self.rfile.read(size))
            command = request.get("command") if isinstance(request, dict) else None
            if not isinstance(command, str) or not command.strip() or len(command) > 256:
                raise ValueError
        except (ValueError, TimeoutError):
            self.json(400, {"error": "Envie um comando válido."})
            return

        with self.server.command_lock:
            try:
                message = player.HELP if command.strip().lower() == "help" else player.execute(self.server.save, command)
                state = self.server.save.read(view)
            except (WorldError, sqlite3.Error, OSError) as error:
                self.json(400, {"error": str(error)})
                return
        self.json(200, {"message": message, "state": state})


def serve(save: Save, port: int, *, open_browser: bool = False) -> None:
    with GameServer(save, port) as server:
        print(f"Living World: {server.origin}/", flush=True)
        print("Para fechar o servidor, pressione Ctrl+C neste terminal.", flush=True)
        if open_browser:
            webbrowser.open(server.origin)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
