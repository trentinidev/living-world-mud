# Architecture

The CLI calls the `Save` application boundary. `Save` owns SQLite transactions and passes an in-memory world to `Simulation`. The simulation validates typed intents, resolves the event queue, and emits structured events. Village content and need rules live in `village.py`. Read-only summaries derive accounting totals from committed inventory and event movements.

## Time and actions

The clock measures integer minutes. The calendar currently defines the number of minutes per day. Each queue entry is ordered by scheduled minute, priority, then a persisted sequence. At a shared minute, action completions run before NPC decisions. Newly scheduled entries must be in the future. A configurable event limit bounds the work in an advance. An advance that exceeds the limit rolls back so it can be retried in smaller intervals.

An intent starts immediately after validation and ends after a positive duration. For each actor, at most one action can be in progress. The engine derives reservations from outgoing movements for pending actions and subtracts them from available stock. At completion it releases the action's own hold, revalidates access and funding against the remaining holds, and commits the whole operation. Cancellation or failed completion releases the hold. The same action ID and intent return the original action, including its terminal status. A conflicting intent under the same ID is rejected.

## Persistence and replay

Each save contains a versioned world snapshot and an append-only causal journal. The snapshot contains rules and content identifiers, the validated configuration, actor state, balances, actions, queue, sequences, and random state. SQLite uses a tagged application ID and a schema migration list. Version 1 is the initial schema.

All mutations use `BEGIN IMMEDIATE` to serialize writers and commit the snapshot and events together. A reader sees one committed snapshot for both state and journal. The SHA-256 digest uses the canonical JSON snapshot with sorted keys and explicit queue order. Tests also compare the full committed journal. World generation and village harvest use separate seeded random sequences. Replay covers equivalent ordered inputs under the same supported runtime and content.

## Food, labor, and needs

The farmstead starts with a finite seed reserve, a pantry, and explicit personal coin allocations. A harvest uses one seed unit to produce a seeded integer yield. Farmhands receive a fixed wage from the farm owner when the harvest completes. A purchase exchanges one pantry unit for a configurable integer price. A meal takes grain out of the eater's stock and reduces hunger. Harvest raises fatigue and rest clears it.

NPCs act when an activity finishes or at a scheduled wake. They consider food, fatigue, income, and pantry availability in a stable order. The farm owner produces to maintain the pantry. Farmhands can earn more coins when their budgets run low. When prerequisites are unavailable, the journal records why the NPC waited. The original `village` scenario exercises this loop with one pantry and a fixed price.

## Two-farm market

The `market` scenario has two independently funded farms at one location. Each has its own pantry, finite planting seed, owner labor, and one hired field shift. Farmhands may take an available shift at either farm. Every harvest and wage settles against that farm's books.

Farms offer their available pantry stock above a two-grain food reserve. A farm charges the base price when its offer reaches the stocked threshold and twice that price for a smaller positive offer. The threshold is the greater of two units and one third of the configured pantry target, rounded down. Buyers sort by price, then by more available grain, then by stable seller ID. The engine validates the selected quote against current offers at submission and reserves the grain and the exact coins. Settlement validates access and availability again at the accepted price.

The controlled seed shortage removes the primary farm's unreserved seed. Previously reserved work may finish. The worker-loss scenario makes a farmhand permanently unavailable for field work while the worker still needs food. An interrupted harvest releases its seed and wage reservations. Both shocks are recorded in the journal.

## Travel and deliveries

The `routes` world places each farm on a separate two-way road to the market square. The east road takes 20 simulated minutes and the west road takes 45. A traveler crossing between fields must pass through the square. Work requires arrival at the corresponding field and trade requires arrival at the square.

Each farm holds seed and grain in a field pantry. Farmers reserve surplus grain for a trip to their market stall. On arrival the grain moves into the stall and becomes eligible for a sale. A cancellation releases the reservation and keeps the actor at the last reached site. Stalls offer their delivered stock even when the farmers return to the fields.

Farmhands choose work using projected public shift availability and distance. Workers and shoppers reserve shifts and sales once they arrive. Personal food travels with its owner, while the simulator accounts for each producer's cash in one wallet.

## Woodland and hearths

The `firewood` world adds a woodcutter and a woodland 35 minutes from the square. A 70-minute cutting job converts up to three units of standing wood into bundles at the woodpile. The default stock is 240 and stays finite. A timed delivery reserves bundles at the woodpile and moves them to the stall on arrival. Each sale reserves a delivered bundle and two coins and then moves both through the normal settlement transaction.

Farm owners buy fuel when tired and their hearth is cold. Burning a bundle at home warms the hearth for one simulated day from completion. A farmhouse rest that finishes while the hearth is warm clears fatigue. A cold farmhouse rest relieves one work shift's fatigue. Each owner's warmth expiration is part of the world snapshot.

## Charcoal kiln

The `charcoal` world adds a burner and a kiln 25 simulated minutes from the market. The burner buys from the woodcutter's stall through the same purchase action and price as farm households. The purchased bundles travel with the buyer. A batch requires the burner and two bundles at the kiln and takes 160 simulated minutes. Completion consumes the bundles and creates one unit of charcoal in the fixed kiln stock. Cancellation releases the reserved bundles.

The burner has 18 starting coins, shares the village grain market, and can take available farm shifts when short on money. The burner pauses charcoal production at a target of four units. Charcoal accumulates at the kiln for the future smelting chain.

## Mine and ore deliveries

The `mining` world adds a miner and a mine 40 simulated minutes from the square. A 100-minute shift at the mine reserves and extracts up to three units of iron ore. The finite deposit starts at 120 units. Extraction records a debit to the deposit and a matching credit to mine stock.

A delivery reserves the ore at the mine. Arrival credits the miner's market stall in the same transaction that moves the miner. The miner aims to keep six units at the stall and can take paid farm shifts when short on food money. The stall holds ore in preparation for the smelting slice.

See [ADR 0001](adr/0001-transactional-snapshot.md) for persistence, [ADR 0002](adr/0002-standing-grain-offers.md) for pricing, [ADR 0003](adr/0003-village-travel.md) for travel, [ADR 0004](adr/0004-firewood-and-hearths.md) for hearths, [ADR 0005](adr/0005-charcoal-batches.md) for charcoal, [ADR 0006](adr/0006-ore-extraction-and-delivery.md) for ore, and [Progress](PROGRESS.md) for observed results.
