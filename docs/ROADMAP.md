# Roadmap

The master prompt is the acceptance specification. Advance in small slices and keep prior invariants under test.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Deterministic laboratory, SQLite state, causal journal, headless CLI | Verified |
| 1 | Autonomous village, needs, work, travel, food and industrial inputs, local market | Food and tool supply chains, seed saving, and paid seed trade verified in the small village. The 31-NPC `hamlet` passes the ten-seed baseline run (see Progress). Labor flexibility and the full disruption set remain |
| 2 | Playable civilian loop, blacksmithing, learning, funded contracts | Planned |
| 3 | Relationships, beliefs, local reputation, independent social activity | Planned |
| 4 | Several settlements, routes, transport, trade, weather and migration | Planned |
| 5 | Ecology, exploration, crime, danger and autonomous expeditions | Planned |
| 6 | Institutional budgets, government, religion, factions and costly magic | Planned |
| 7 | Generations, inheritance, history and larger-scale fantasy | Planned |
| 8 | Authenticated multiplayer with authoritative commands and private views | Planned |
| 9 | Narrative and accessibility polish, optional local-first text generation | Planned |

## Next Phase 1 slice

The `hamlet` scenario has 31 NPCs, 8 locations, 7 occupations and 10 tracked goods. It meets the Phase 1 size targets. Remaining gate work:

1. Labor flexibility. Only farmhands and the woodcutter switch work by income need. The charcoal burner, miner, smelter, and blacksmith should also fall back to paid work when demand for their output stalls, and idle farmhands should be able to take craft work.
2. A repeatable `report` command that runs the ten-seed baseline at 1, 7, 30 and 90 days. It should export the population, needs, production, consumption, stock, market activity, money accounting, and runtime. This replaces the ad hoc batch script.
3. Hamlet disruption cases with documented acceptance criteria: seed shortage, worker loss, an empty ore deposit, an empty woodland, and competition for the last stall item.
4. Data-driven farms and roads. Replace the fixed two-farm road table so a village can generate more farms and households.
