# 0011 — Hamlet population and multiple hired field shifts

## Status

Accepted.

## Context

The Phase 1 gate asks for a village of roughly 30–50 NPCs. The `seed-trade` scenario has seven actors, and each farm can hire only one field worker at a time. Adding households without more paid work would just leave them unemployed and hungry.

## Decision

- Add a separate `hamlet` scenario with content version `village-hamlet-1`. It reuses the full `seed-trade` chain (two farms, woodland, kiln, mine, smeltery, forge, hoes, seed saving and paid seed trade) and keeps the smaller scenarios unchanged for regression.
- A new nested `hamlet` configuration sets `farmhands` (default 24, at most 40) and `hired_shifts_per_farm` (default 6). With the five craft workers and two farm owners, the default population is 31 NPCs.
- A farm can run up to `hired_shifts_per_farm` concurrent hired harvests in the hamlet. Each shift still reserves the farm's wage and one planting seed when it starts, so the farm's cash and seed limit how many it can actually fund. Other content versions keep one shift per farm.
- Farmhand names are sampled from the original eight-name catalog first. Generated names from fixed syllable lists are drawn only when more than eight are needed, so earlier seeds keep the same names and digests.
- In the hamlet, the woodcutter takes paid field shifts when the woodland and woodpile are empty, or when cash falls below four meals while firewood sits unsold at the stall. The first 90-day batch found a seed where firewood demand stopped around day 51 and the woodcutter spent their savings and reached the hunger cap by day 70. The rule switches occupations by income need. It does not add money or food. Other scenarios keep the woodcutter in forestry so their digests stay fixed.
- The `hamlet` configuration is omitted from snapshots of other content versions while it has its default value, preserving earlier digests.

## Consequences

The hamlet is the first population-scale baseline. Location count, occupation variety, and goods remain those of the smaller chain. Expanding farms and households beyond two farm owners requires turning the fixed road table into world data.
