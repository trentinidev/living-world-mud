# Living World repository guide

Read [Progress](docs/PROGRESS.md), [Roadmap](docs/ROADMAP.md), and the relevant [architecture notes](docs/ARCHITECTURE.md) before choosing a slice. Keep progress, acceptance evidence, and architectural decisions current. The master prompt and its Portuguese companion define the long-term product vision.

## Commands

- Install the package with `python -m pip install -e .`. Install the optional test dependency with `python -m pip install -e ".[test]"`.
- Run `python -m pytest -q`. For an offline run from source, set `PYTHONPATH=src` and run `python -m unittest discover -s tests -v`.
- Run `python -m living_world scenario lab --seed 42 --json` and `python -m living_world scenario tools --seed 8 --days 7 --json` for smoke checks. The market scenarios also accept `--shock seed-shortage` or `--shock worker-loss` for paired cases.

## Simulation conventions

- Use integer simulation minutes and schedule future events by minute, priority, then persisted sequence. Action completions have priority over NPC decisions.
- Validate typed intents through the simulation. Treat a started action's outgoing resource movements as reservations. Revalidate access and funding at completion.
- Record initialization, source and sink movements, and transfers. Goods and coins must stay nonnegative. World state, sequence counters, random state, and journal entries commit in the same transaction.
- In the market scenario, quote from unreserved stock and lock the accepted price when the sale starts. Preserve both resource holds until settlement or cancellation.
- In the routes scenario, check actor location for work and trade. A pending trip reserves cargo at its source, and the goods move to the destination account atomically on arrival.
- In the firewood scenario, record standing-wood loss and firewood production together. A hearth consumes purchased fuel and updates the persisted expiry of its warmth.
- The charcoal burner uses the same funded firewood purchase as households. A kiln batch reserves its inputs and records consumption and output together on completion.
- Mining moves ore out of the finite deposit and into mine stock on shift completion. Deliveries reserve mine stock and move the reserved cargo to the miner's stall on arrival.
- Ore and charcoal purchases debit the buyer and credit the supplier. A smelting batch reserves both inputs and credits iron only on completion.
- In the blacksmith scenario the smelter delivers iron to a stall, an iron purchase pays the smelter, and a forging job consumes reserved iron on completion.
- A farm holds at most one installed hoe. The active harvest reserves it, completion applies the bonus and one use of wear, and the last use removes the hoe from inventory.
- In `seed-saving`, harvest completion spends the planted seed and divides the crop between edible grain and planting seed in the same transaction. Keep these outputs separate in the journal and summary. Set `seed_reserve_target` to zero in a matched control.
- The `hamlet` scenario reuses the seed-trade rules with a larger population and allows `hamlet.hired_shifts_per_farm` concurrent hired harvests per farm. It derives farm accounts and roads from `hamlet.farms`. Other scenarios keep one hired shift per farm. Draw generated farmhand names only beyond the original eight so earlier digests stay fixed.
- At the hamlet forge, the blacksmith unloads iron into the workshop. A hired forge shift reserves both workshop iron and the worker's wage. One shift can run at a time.
- Advance long hamlet runs in one-day steps to stay under `max_events_per_advance`. Use `python -m living_world report hamlet --seeds 0-9 --days 1,7,30,90` to run the Phase 1 baseline and reconcile the journal with saved balances.
- A playable hamlet is created with `create --scenario hamlet --player NAME` and opened with `play`. Keep player commands on the same intent and reservation paths as NPC actions. Player reads leave the clock untouched, and the NPC scheduler skips the player.
- Use `web --save PATH --open` to play a character save in a local browser. Keep the server bound to loopback, its mutations on the existing player command path, and the browser view derived from the save.
- The `civilian` scenario adds forge fuel, blacksmithing experience and tracked hoes. Grant experience on completion. A hoe's record must follow its journaled inventory movements through sale, installation, wear and retirement.
- In `contracts`, a funded order transfers money to the issuing farm's escrow. Settlement reserves the exact qualifying hoe and the payment. An expired order refunds the farm. Keep delivery, collection and ordinary sales on the shared reservation and item-tracking paths.
- In `apprenticeship`, a lesson occupies the forge and Ada until it completes or is canceled. The hammer recipe comes from the completed lesson. A hammer changes quality and wears only when a forging action finishes.
- Keep world rules independent of wall-clock time, disk, user interfaces, and networking. Use explicit ordering and stable seeds. Verify interrupted continuation as well as repeat-run determinism.
- Keep saves out of source control. Change rules, content, or schema versions deliberately when changing save or replay semantics.
- Implement the smallest useful slice and run the existing tests before advancing a phase. Preserve real adverse outcomes, such as running out of seed, and record observed results and limitations.
