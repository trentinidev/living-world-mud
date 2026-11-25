# 0017 — Local browser play uses the same save

## Decision

The `web` command opens one character save on a loopback HTTP server. The browser receives an authoritative view of the character, visible roads, and local offers. Buttons send the same commands as the terminal to the existing player adapter. The SQLite transaction commits the action, inventory, clock, NPC decisions, and journal together.

The server uses the standard library and bundled page assets. Mutation requests require the local origin. A user can close or reload the browser and resume the save while the server is open.
