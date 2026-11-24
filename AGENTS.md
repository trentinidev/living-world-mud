# Living World repository guide

Read [Progress](docs/PROGRESS.md), [Roadmap](docs/ROADMAP.md), and the relevant [architecture notes](docs/ARCHITECTURE.md) before choosing a slice. Keep progress, acceptance evidence, and architectural decisions current. The master prompt and its Portuguese companion define the long-term product vision.

## Commands

- Install the package with `python -m pip install -e .`. Install the optional test dependency with `python -m pip install -e ".[test]"`.
- Run `python -m pytest -q`. For an offline run from source, set `PYTHONPATH=src` and run `python -m unittest discover -s tests -v`.
- Run `python -m living_world scenario lab --seed 42 --json` and `python -m living_world scenario mining --seed 8 --days 1 --json` for smoke checks. The market scenarios also accept `--shock seed-shortage` or `--shock worker-loss` for paired cases.

## Simulation conventions

- Use integer simulation minutes and schedule future events by minute, priority, then persisted sequence. Action completions have priority over NPC decisions.
- Validate typed intents through the simulation. Treat a started action's outgoing resource movements as reservations. Revalidate access and funding at completion.
- Record initialization, source and sink movements, and transfers. Goods and coins must stay nonnegative. World state, sequence counters, random state, and journal entries commit in the same transaction.
- In the market scenario, quote from unreserved stock and lock the accepted price when the sale starts. Preserve both resource holds until settlement or cancellation.
- In the routes scenario, check actor location for work and trade. A pending trip reserves cargo at its source, and the goods move to the destination account atomically on arrival.
- In the firewood scenario, record standing-wood loss and firewood production together. A hearth consumes purchased fuel and updates the persisted expiry of its warmth.
- The charcoal burner uses the same funded firewood purchase as households. A kiln batch reserves its inputs and records consumption and output together on completion.
- Mining moves ore out of the finite deposit and into mine stock on shift completion. Deliveries reserve mine stock and move the reserved cargo to the miner's stall on arrival.
- Keep world rules independent of wall-clock time, disk, user interfaces, and networking. Use explicit ordering and stable seeds. Verify interrupted continuation as well as repeat-run determinism.
- Keep saves out of source control. Change rules, content, or schema versions deliberately when changing save or replay semantics.
- Implement the smallest useful slice and run the existing tests before advancing a phase. Preserve real adverse outcomes, such as running out of seed, and record observed results and limitations.
