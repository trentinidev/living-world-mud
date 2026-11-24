# Progress

## Sixth checkpoint — iron ore mining and deliveries

The `mining` scenario adds a miner, a finite deposit, and a market stall for iron ore. Extraction debits the deposit and credits mine stock. Deliveries reserve ore at the mine and move it to the market on arrival. The miner has a six-unit stock target and can take paid field work.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario mining --seed 8 --minutes 158 --json
python -m living_world scenario mining --seed 8 --minutes 159 --json
python -m living_world scenario mining --seed 8 --days 1 --json
```

All 47 tests passed in the installed Windows environment. The new tests cover last partial shifts, empty deposits, role and route validation, cancellation and rebooking, persistence during delivery, and full inventory reconciliation. The earlier charcoal scenario retained its seed-8 digest.

The seed-8 miner extracted three units at minute 118. The load reached the market at minute 159, then a second load arrived at minute 453. At the end of day one the stall held six units and the deposit held 114. A saved run advanced through minutes 140, 158, and 159 and then to day one matched the direct runs.

A batch of 60 independent runs used seeds 0–9 at baseline horizons of 1, 7, 30, and 90 days and with two-unit and empty deposits for seven days. It took about 23.1 seconds. All runs reconciled grain, seed, wood, charcoal, ore, and the 72-coin supply. Every baseline run delivered six units by day one. Every two-unit case depleted its deposit and delivered two units. Empty deposits left the ore stall empty while the village continued to produce charcoal, grow grain, and feed residents.

### Remaining Phase 1 work

The ore stall accumulates stock for the first smelter. Smelting will add paid demand for ore and charcoal and produce iron as the next inventory good.

## Fifth checkpoint — charcoal kiln

The `charcoal` scenario adds a kiln and a burner who buys from the same firewood stall as households. The burner carries fuel to the kiln. Each batch takes 160 simulated minutes and converts two firewood into one charcoal unit. The burner's production target is four units of stored charcoal.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario charcoal --seed 8 --minutes 350 --json
python -m living_world scenario charcoal --seed 8 --minutes 440 --json
python -m living_world scenario charcoal --seed 8 --days 1 --json
```

All 41 tests passed in the installed Windows environment. Tests cover physical access, input validation, batch cancellation and retry, exact conservation, and a household and a kiln order competing for the final bundle. A separate save advanced through minutes 350 and 440 and then to day one matched the direct runs. The earlier firewood scenario retained its seed-8 digest.

In seed 8, a farmer paid for firewood at minute 168 and the burner bought the first two bundles at minutes 241 and 250. The first batch finished at minute 437. By day one the burner had bought and used eight bundles for four charcoal units. Households bought two bundles from the same stall.

A batch of 50 independent runs used seeds 0–9 across baseline horizons of 1, 7, 30, and 90 days and a seven-day case with zero starting standing wood. It took about 16.0 seconds. All runs reconciled grain, standing wood, firewood, charcoal, and the 66-coin supply. By day seven every baseline run had reached four units of charcoal. The zero-stock runs had no kiln purchases, charcoal production, or heated rests.

### Remaining Phase 1 work

Charcoal currently accumulates at the kiln. The burner can take paid field work after stocking the kiln or when production funds run low. The next slice adds an ore deposit, a miner, and ore transport. A later smelter gives both ore and charcoal a production use.

## Fourth checkpoint — firewood and farm hearths

The `firewood` scenario adds a woodland, a woodcutter, and farm hearths. Cutting transfers standing wood into a woodpile as firewood. The woodcutter carries bundles to the square and sells them for two coins each. Farm owners buy fuel and burn it at home. A warm hearth improves fatigue recovery.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario firewood --seed 8 --minutes 100 --json
python -m living_world scenario firewood --seed 8 --minutes 125 --json
python -m living_world scenario firewood --seed 8 --days 1 --json
```

All 35 tests passed on the installed Windows environment. New tests cover depletion, delivery cancellation and rebooking, competing buyers, funded settlement, warm and cold rests, and ledger reconstruction after save and reload. The earlier routes demo retained its seed-8 digest.

The seed-8 journal recorded the first cut at minute 88, the first delivery at minute 124, the first sale at minute 194, and the first hearth burn at minute 226. Both farms burned one bundle on day one. Four rests finished at warm hearths. A save advanced through minutes 100 and 125 and then to day one matched the direct runs.

A batch of 50 independent runs used seeds 0–9 across baseline horizons of 1, 7, 30, and 90 days and a seven-day case with zero starting standing wood. The batch took about 12.1 seconds. Every run reconciled grain, standing wood, firewood, and the 48-coin supply. Day-90 baseline runs cut 102–126 bundles and burned 99–120. In the zero-stock case, extraction, sales, burning, and heated rests stayed at zero.

### Remaining Phase 1 work

The first implementation has one woodcutter, a fixed bundle price, no regrowth, and heat for farmhouses. The woodcutter's income comes from fuel sales. Tight household budgets can leave the woodcutter hungry even when there is standing wood. The next slice adds competing kiln demand. Open questions include regrowth rates, seasonal fuel demand, and when woodcutters should look for other work.

## Third checkpoint — travel and deliveries

The `routes` scenario separates the fields and market square. The east road takes 20 simulated minutes and the west road takes 45. Harvesting requires presence at the field, and buying requires presence at the square. Each producer has a field pantry and a market stall. Deliveries reserve grain at the field and move it to the stall on arrival.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario routes --seed 8 --minutes 50 --json
python -m living_world scenario routes --seed 8 --minutes 70 --json
python -m living_world scenario routes --seed 8 --days 7 --json
python -m living_world scenario routes --seed 8 --days 7 --shock seed-shortage --json
python -m living_world scenario routes --seed 8 --days 7 --shock worker-loss --json
```

All 29 tests passed in the installed Windows environment. The new tests verify travel durations, physical access, unavailable cargo, mid-trip continuation, safe cancellation and replacement, and inventory reconstructed from the journal. The prior `market` scenario retained its seed-8 digest.

The seed-8 east delivery reached the square at minute 47 and the west delivery at minute 65. At minute 50 only the east stall offered grain. By minute 70 both stalls did. A save advanced for 50 and then 20 minutes matched the direct 70-minute run.

### Seven-day seed-8 results

| Scenario | Grain harvested | Grain delivered | Grain eaten | East road trips | West road trips | West farm sales |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 101 | 50 | 80 | 74 | 66 | 20 |
| East seed shortage | 89 | 59 | 80 | 21 | 102 | 43 |
| One farmhand loses field-work capacity | 95 | 37 | 67 | 68 | 25 | 6 |

A batch of 60 independent runs used seeds 0–9 across four baseline horizons of 1, 7, 30, and 90 days and both seven-day shocks. It took about 11.0 seconds. Every run conserved the 42-coin supply, reconciled its grain and seed balances, and recorded harvest, deliveries, purchases, and food consumption. Day-90 baseline runs completed 1,758–1,788 trips, delivered 548 grain, and consumed 1,076 grain.

### Remaining Phase 1 work

The route graph is fixed and travel costs time. Trip cancellation leaves the actor and cargo at the origin. Carriers and buyers use standing stalls and share knowledge of public shift availability within this settlement. The next slice adds woodland work and firewood as a second market good. Open design questions include what household needs should consume firewood and how often woodland stock should renew.

## Second checkpoint — two-farm market

The `market` scenario adds two independent grain producers, a hired shift at each farm, finite standing offers, and integer prices based on available stock. NPCs switch sellers and seek work at either farm. Purchases hold the exact grain and quoted coins until completion or cancellation. The original `village` scenario remains available with its seed-42 digest.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario market --seed 8 --days 7 --json
python -m living_world scenario market --seed 8 --days 7 --shock seed-shortage --json
python -m living_world scenario market --seed 8 --days 7 --shock worker-loss --json
```

All 23 tests passed with the installed Windows environment. The new tests cover a price increase after a reservation, accepted-price settlement after reload, competing claims on a final offer, supplier switching, ledger reconstruction after seed loss, cancellation and reassignment of an interrupted field shift, and deterministic continuation across saves. A persistent seed-42 market advanced for one day and then six days matched the single seven-day run.

### Seven-day seed-8 results

| Scenario | Grain harvested | Grain eaten | Primary farm sales | West farm sales | Sales at two coins |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 92 | 80 | 26 | 14 | 0 |
| Primary seed shortage | 83 | 80 | 5 | 45 | 1 |
| One farmhand loses field-work capacity | 73 | 67 | 20 | 7 | 0 |

The seed-shortage run moved sales to the west farm while maintaining food consumption. In the worker-loss run, harvests dropped from 32 to 26. The sidelined farmhand eventually ran short of money and reached the hunger cap. The coin supply stayed at 42 in all three runs.

A batch of 60 independent market runs used seeds 0–9 across four baseline horizons of 1, 7, 30, and 90 days and both seven-day shocks. All runs conserved coins, reconciled grain and seed movements, and recorded production, consumption, and purchases. The batch took about 9.2 seconds on the bundled Windows runtime. Day-90 baseline production ranged from 1,085 to 1,107 grain, with 1,076 eaten and 538 purchases in each seed. In the seven-day shortage batch, one of ten seeds paid a higher price. For the other nine, buyers could keep shopping at the base price.

### Remaining Phase 1 work

The two farms currently share one location, the price rule uses two bands, and the worker-loss shock lasts for the entire run. The next slice adds travel between farms and market. Open questions include how a farmer should divide grain between reserves and sales, and when individual workers should switch jobs based on commute and wages. The Phase 1 gate also calls for more occupations and material chains.

## First implementation checkpoint

Phase 0 passed its acceptance tests. The first Phase 1 slice runs an autonomous food, wage, purchase, and rest loop at a three-NPC farmstead.

### Verification

On Windows with Python 3.12.14 and SQLite 3.53.1, all 16 tests passed with `PYTHONPATH=src`.

```sh
python -m unittest discover -s tests -v
python -m living_world scenario lab --seed 42 --json
python -m living_world scenario village --seed 42 --days 7 --json
python -m living_world scenario village --seed 42 --days 7 --config saves/shortage.json --json
```

The project configures pytest as an optional development dependency. It was absent from the bundled runtime, and the package index returned no installable distribution in this environment. The same test cases ran with `unittest`.

I also verified the Windows editable install with `python -m pip install --no-build-isolation --no-index -e .` using a virtual environment with access to the bundled build tools. Setuptools could not expand the sandbox's default temporary directory because its name contains braces. The build succeeded with a workspace-local temporary directory. The installed `living-world` entry point matched the source-tree run, and all 16 tests passed from the installed environment.

The tests cover replay and save/load continuation, scheduler ties, validation, cancellation, retry idempotency, injected SQLite failures, finite purchase reservations across separate connections, and reconstruction of the full village inventory from its journal. The seed-42 lab delivered two grain and ended with 13 grain across the two actors. The saved village CLI produced the same digest as the temporary scenario after seven days.

### Headless results

The seed-42 village completed 24 harvests, 40 meal purchases, and 12 rests over seven days. It produced 65 grain, consumed 60, and ended with 10 grain after starting with five. Wages and meal purchases each moved 40 coins over the run. The total supply remained 24 coins.

In the same seeded world with `{"village":{"starting_seed":0}}`, the pantry emptied after five meals and production stayed at zero. Both farmhands reached the configured hunger cap. Coins remained conserved. This scenario models a supply failure with the current fixed price.

The benchmark created independent temporary saves for seeds 0–9 at each horizon and advanced them with `Save.advance(days=...)`. It checked stock, seed and money accounting after each run. All 40 runs showed production, purchases and consumption with zero failed completions. The batch took approximately 5.1 seconds in the bundled runtime, including save creation, advancement, and reporting.

| Simulated days | Harvests | Purchases | Grain produced | Grain eaten | Seed remaining |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 3–4 | 4 | 7–11 | 6 | 396–397 |
| 7 | 21–24 | 40 | 65–69 | 60 | 376–379 |
| 30 | 89–94 | 178 | 272–280 | 267 | 306–311 |
| 90 | 271–277 | 538 | 811–824 | 807 | 123–129 |

### Remaining work and open questions

The current economy has one pantry, a fixed meal price, and a finite seed reserve. Hunger is capped and affects choices. Health, incapacitation, travel, worker replacement, market pricing, and additional production chains are pending. The 90-day benchmark measures this farmstead prototype. Village-scale viability remains a Phase 1 gate.

The next slice will test how two producers, finite offers, and stock-sensitive prices respond to a shortage or worker loss. Open design questions include when households should save grain for planting, how quickly labor should switch suppliers or roles, and what sustained hunger should do to health and productivity.
