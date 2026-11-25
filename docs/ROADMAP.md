# Roadmap

The master prompt is the acceptance specification. Advance in small slices and keep prior invariants under test.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Deterministic laboratory, SQLite state, causal journal, headless CLI | Verified |
| 1 | Autonomous village, needs, work, travel, food and industrial inputs, local market | Verified. All ten baseline seeds passed at day 90. Shortage, worker loss, market competition and labor reallocation were verified. |
| 2 | Playable civilian loop, blacksmithing, learning, funded contracts | Verified for local play. Matched civilian saves and both the terminal and browser interfaces passed. |
| 3 | Relationships, beliefs, local reputation, independent social activity | Planned |
| 4 | Several settlements, routes, transport, trade, weather and migration | Planned |
| 5 | Ecology, exploration, crime, danger and autonomous expeditions | Planned |
| 6 | Institutional budgets, government, religion, factions and costly magic | Planned |
| 7 | Generations, inheritance, history and larger-scale fantasy | Planned |
| 8 | Authenticated multiplayer with authoritative commands and private views | Planned |
| 9 | Narrative and accessibility polish, optional local-first text generation | Planned |

## Phase 1 acceptance

The default `hamlet` has 31 NPCs, eight locations, seven occupations and ten tracked goods. It supports two to six farms and paid shifts in the fields and at the forge. The report includes the day 1, 7, 30 and 90 snapshots and checks the causal ledger against saved balances. See [Progress](PROGRESS.md) for the baseline and disruption results.

## Phase 2 acceptance

The [economy acceptance results](PROGRESS.md#eighteenth-checkpoint--phase-2-economy-acceptance) cover the civilian career loop and matched saves. Use `web --save PATH --open` to play the same save in a local browser.

The next phase starts with NPC memories of completed transactions and follows how that evidence changes supplier choice.
