import json
import tempfile
import unittest
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from living_world.persistence import Save
from living_world.player import execute
from living_world.web import GameServer


class WebTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.save = Save.create(self.directory / "browser.db", 8, scenario="apprenticeship", player_name="Iara")
        self.server = self.enterContext(GameServer(self.save, port=0))
        thread = Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.shutdown)

    def get(self, path, headers=None):
        return urlopen(Request(self.server.origin + path, headers=headers or {}), timeout=5)

    def send(self, command, origin=None):
        headers = {"Content-Type": "application/json", "Origin": origin or self.server.origin}
        request = Request(self.server.origin + "/api/command", json.dumps({"command": command}).encode(),
                          headers=headers)
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_browser_commands_commit_the_same_journal_as_the_terminal(self):
        with self.get("/") as response:
            self.assertIn(b"Living World", response.read())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        for path in ("/style.css", "/game.js"):
            with self.get(path) as response:
                self.assertTrue(response.read())
        control = Save.create(self.directory / "terminal.db", 8, scenario="apprenticeship", player_name="Iara")
        with self.get("/api/state") as response:
            state = json.load(response)
        self.assertEqual((state["name"], state["coins"], state["minute"]), ("Iara", 3, 0))
        self.assertIsNone(state["market"])
        for command in ("work", "go market-square", "buy", "eat"):
            result = self.send(command)
            self.assertEqual(result["message"], execute(control, command))
        self.assertEqual((result["state"]["coins"], result["state"]["grain"]), (4, 0))
        self.assertEqual(result["state"]["location"], "market-square")
        self.assertEqual(self.save.inspect(journal=True), control.inspect(journal=True))
        self.save.audit_inventory()

    def test_failed_commands_and_foreign_requests_leave_the_save_unchanged(self):
        initial = self.save.inspect(journal=True)
        with self.assertRaises(HTTPError) as foreign:
            self.send("work", origin="http://other-site.example")
        with foreign.exception as response:
            self.assertEqual(response.code, 403)
        with self.assertRaises(HTTPError) as host:
            self.get("/api/state", {"Host": f"other-site.example:{self.server.server_port}"})
        with host.exception as response:
            self.assertEqual(response.code, 403)
        with self.assertRaises(HTTPError) as rejected:
            self.send("buy")
        with rejected.exception as response:
            self.assertEqual(response.code, 400)
            self.assertIn("visit market-square", json.load(response)["error"])
        self.assertEqual(self.save.inspect(journal=True), initial)
