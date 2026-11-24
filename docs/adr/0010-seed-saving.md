# ADR 0010 — Save planting seed from harvests

## Decision

The `village-seed-saving-1` content completes a harvest by consuming one planting seed and dividing the resulting crop into food and planting seed. It includes any hoe bonus before making the division. Each farm targets four seed units by default, counted after spending the seed for the current harvest. At most half the crop, rounded down, can go toward that target. A target of zero sends the full crop to food and provides a control for low-seed experiments.

The split uses the farm's current inventory at harvest completion. It credits food and seed as separate journal movements in the transaction that pays any wages and applies tool wear. The village report keeps `grain_produced` as edible output and adds totals for seed planted, seed saved, and the combined crop.

## Consequences

Each harvest yields food, including a one-grain crop. Building a reserve trades some immediate food for future harvests. A farm with zero seeds cannot start a harvest. Trade between farms would give a farm in that situation a way to replant using a neighboring surplus.
