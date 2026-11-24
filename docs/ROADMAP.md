# Roadmap

The master prompt is the acceptance specification. Advance in small slices and keep prior invariants under test.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Deterministic laboratory, SQLite state, causal journal, headless CLI | Verified |
| 1 | Autonomous village, needs, work, travel, food and industrial inputs, local market | Grain, travel, hearths, charcoal, and ore deliveries verified |
| 2 | Playable civilian loop, blacksmithing, learning, funded contracts | Planned |
| 3 | Relationships, beliefs, local reputation, independent social activity | Planned |
| 4 | Several settlements, routes, transport, trade, weather and migration | Planned |
| 5 | Ecology, exploration, crime, danger and autonomous expeditions | Planned |
| 6 | Institutional budgets, government, religion, factions and costly magic | Planned |
| 7 | Generations, inheritance, history and larger-scale fantasy | Planned |
| 8 | Authenticated multiplayer with authoritative commands and private views | Planned |
| 9 | Narrative and accessibility polish, optional local-first text generation | Planned |

## Next Phase 1 slice

Add a smelter who buys iron ore and charcoal. Use a timed batch to consume both inputs and produce iron. Test that a shortage of either input stops the batch and that purchases fund the miner and charcoal burner.

The full Phase 1 gate also requires broader occupational and location coverage, labor reallocation, additional material chains, and measured village viability at day 90. Keep the current prototype as a small regression scenario.
