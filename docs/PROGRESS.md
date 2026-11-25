# Progress

## Thirteenth checkpoint — hamlet employment, additional farms, and disruption tests

The `hamlet` now gives farmhands access to paid forge shifts. The blacksmith moves purchased iron into the forge before a shift can reserve it. A hired shift also reserves the wage. The worker earns it when the hoe is finished. Craft workers can take field shifts when their usual work is unavailable and they need income. The default village still has 31 residents and eight locations. Increasing `hamlet.farms` to four produced a village with 33 residents and ten locations. All four farms harvested and sold grain in the seven-day run.

All 92 tests passed. They cover the last item at the stall, insufficient funds, the forge's single shift, worker loss during a forge shift, and checking saved balances against the journal. A save from `village-hamlet-1` resumed under the new code with the same digest as it did under the original code.

The seven-day experiments used seeds 0, 8 and 9, with a control and four disruptions per seed. All 15 runs reconciled their journals, preserved 222 coins, and recorded zero failed completions.

| Disruption | Observed result |
| --- | --- |
| East farm seed shortage on day one | The east farm bought a seed and returned to a four-seed reserve in all three runs. In seed 8 the two-coin food purchases rose from 208 to 222. |
| One farmhand unable to work after day one | The active farmhand pool fell from 24 to 23. Total grain eaten fell from 620 to 604–607. In seed 0 the smelter took a field shift. |
| Empty ore deposit | No ore was extracted and no iron or hoes were produced. The miner completed 11–14 paid field shifts. |
| Empty woodland | No wood, charcoal, iron, or hoes were produced. The woodcutter completed 13–14 paid field shifts. |
| Two buyers for the last grain at a stall | A focused test confirmed one successful payment and delivery. The second order left the journal and balances unchanged. |

### Phase 1 acceptance

The installed Windows CLI ran `report hamlet --seeds 0-9 --days 1,7,30,90 --json` in 189.01 seconds. All ten seeds met the day-90 criteria, above the required nine. Every ledger reconciled, every village retained its 222 coins, and no action failed at completion.

At day 90, each village had 31 NPCs and zero at the hunger cap. During days 84–90, each completed 388–414 harvests and 609 food purchases and ate 650–651 grain. The villages finished with 2,641–3,307 edible grain in stock. The report includes population, hunger, paid work, production, consumption, market activity, stock by good and runtime at the recorded checkpoints.

Phase 1 is complete. The next phase begins with player character creation and text commands through the same action rules used by NPCs.

## Twelfth checkpoint — 31-resident hamlet and viability report

The `hamlet` added 24 farmhands, six hired shift slots per farm, and an alternative paid job for the woodcutter when wood or buyers ran out. It retained the eight locations and the full food-to-tool chain. The `report` command was added for repeatable multi-seed runs at 1, 7, 30 and 90 days. The existing suite contained 88 passing tests at this checkpoint.

## Eleventh checkpoint — paid seed purchases between farms

In the `seed-trade` scenario, a farm owner with an empty seed pantry can travel to a neighboring farm that has unreserved seed above its reserve target. The accepted purchase reserves one seed and two coins. On completion the buyer pays the seller and carries the seed back through the market. A separate action unloads it at home before it can be planted.

In the seven-day seed-8 shortage run, the east farmer paid two coins for a seed and brought it home. The east and west farms completed 37 and 21 harvests respectively and finished with four and 378 seeds. The village paid 56 coins in field wages. In the matched `seed-saving` run, east and west completed eight and 41 harvests, the east reserve remained empty, and the village paid 68 coins in wages. Residents ate 180 grain in each run and the total coin supply stayed at 156.

The 76 existing tests and both seed-trade tests passed. The new tests cover access, reserve protection, insufficient funds, cancellation and retry, and journal equality after resuming a shortage run from a save.

The next slice expands the village population and paid work. The Phase 1 acceptance report still needs the larger village and the complete baseline and disruption runs.

## Tenth checkpoint — save planting seed from harvests

The `seed-saving` scenario extends the farm tool chain. Each completed harvest spends one seed and can set aside up to half its crop, rounded down, to refill the farm's seed reserve. The reserve target defaults to four seed units per farm. The remaining crop goes to the pantry as edible grain. A one-grain crop goes entirely to food. The journal records the two outputs separately.

### Verification

All 76 tests passed in the installed Windows environment. Tests cover the output split, a full reserve, a one-grain harvest, a farm with no seed, two overlapping harvests, hoe bonuses and wear, and resuming a save during a harvest. The earlier `tools` scenario retained its seed-8 digest. Both seven-day commands in the [README walkthrough](../README.md#compare-a-week-with-and-without-saving-seed) were verified with the installed executable.

Both seed-8 villages started with one planting seed per farm. They produced the following results after seven days.

| Measure | Save toward four seeds per farm | Seed saving disabled |
| --- | ---: | ---: |
| Completed harvests | 71 | 2 |
| Seeds saved | 77 | 0 |
| Seed units left per farm | 4 | 0 |
| Edible grain harvested | 205 | 5 |
| Grain eaten by residents | 180 | 15 |
| Farm owner hunger at day seven | 480 | 1,440 |

The paired experiment ran 60 simulations across seeds 0–9 at 7, 30, and 90 days. It took about 67 seconds. Every run reconciled the seed and food balances and the 156-coin supply. At day 90, all runs with seed saving had four seeds per farm and residents had eaten 2,421 grain. The controls all stopped harvesting after two shifts and residents ate 14–17 grain.

### Remaining Phase 1 work

Seed saving requires an initial planting seed. A farm with none still needs a source of seed to restart. The next slice introduces paid seed purchases between farms and tests recovery from an empty reserve.

## Ninth checkpoint — farm tool purchases, yields, and wear

The `tools` scenario connects the forge back to farming. The blacksmith delivers hoes to the market, and farm owners pay 15 coins per hoe. At the farm, a farmer can install one hoe for the owner or a hired worker to use. A completed assisted harvest adds two grain and spends one of eight uses. The final use removes the hoe, letting the farm buy a replacement.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario tools --seed 8 --days 1 --json
python -m living_world scenario tools --seed 8 --days 7 --json
```

All 68 tests passed in the installed Windows environment. A paired harvest used the same seed and planting cost with and without a hoe and measured exactly two extra grain. Tests also cover exclusive reservation, cancellation, wear, purchase and installation, fallback when ore is absent, saved actions, full ledger replay, and the earlier blacksmith digest.

In seed 8, the first farmer paid for a hoe at minute 1088 and installed it at minute 1120. The first assisted harvest finished at minute 1222. The hoe wore out at minute 5023 and a replacement was installed at minute 5276. Seven days produced 29 assisted harvests, 58 bonus grain, three worn hoes, and three installed replacements. Splitting the run at day one matched the direct seven-day run.

A batch of 60 independent runs used seeds 0–9 at 1, 7, 30, and 90 days with both upstream inputs available, plus seven-day cases with an empty ore deposit or an empty woodland. It took about 36 seconds. Every run reconciled materials, tool uses, and the 156-coin supply. At day seven every baseline run had installed three replacements and gained 54–60 bonus grain. At day 90 the baseline range was 352–798 bonus grain. The shortage runs continued ordinary harvests with zero tool purchases or uses.

### Remaining Phase 1 work

Farms can increase yield with tools and go back to ordinary harvests when tools wear out or supplies run short. The next slice lets farms retain part of a crop as seed and checks whether that extends food production under a low-seed start.

## Eighth checkpoint — iron purchases and farm tools

The `blacksmith` scenario adds a forge, a blacksmith, and funded iron purchases from the smelter. The smelter delivers iron to the market. The blacksmith carries purchased iron to the forge and reserves one unit per job. Each job takes 140 simulated minutes and consumes the iron to make one hoe.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario blacksmith --seed 8 --minutes 1039 --json
python -m living_world scenario blacksmith --seed 8 --minutes 1040 --json
python -m living_world scenario blacksmith --seed 8 --days 1 --json
```

All 61 tests passed in the installed Windows environment. Tests cover delivery before purchase, limited funds and stock, exact payment to the smelter, forge access, cancellations and retries, save replay, and full inventory reconciliation. The previous smelting scenario retained its seed-8 digest.

In seed 8, the first iron reached the stall at minute 790. The blacksmith paid the smelter 12 coins at minute 883 and finished the first hoe at minute 1040. A saved run advanced through minutes 950, 1039, and 1040 and then to the end of day one matched the direct runs.

A batch of 60 independent runs used seeds 0–9 at 1, 7, 30, and 90 days with both upstream inputs available, plus seven-day cases with an empty ore deposit or an empty woodland. It took about 28.7 seconds. Every run reconciled materials and the 156-coin supply. All baseline runs produced two hoes by day one and reached three by day seven. They paid the smelter 36 coins in total for three iron. Both shortage cases produced zero iron and zero hoes.

### Remaining Phase 1 work

The blacksmith starts with 42 coins and targets three hoes. Completed tools accumulate at the forge. The next slice lets farmers buy them and measures their effect on farming and the demand caused by wear.

## Seventh checkpoint — paid inputs and iron smelting

The `smelting` scenario adds a smelter, a smeltery, and funded purchases from both the miner and the charcoal burner. The charcoal burner delivers stock to the village market. Each smelting batch reserves two ore and one charcoal, then consumes them and credits one iron after 180 simulated minutes.

### Verification

```sh
python -m unittest discover -s tests -v
python -m living_world scenario smelting --seed 8 --minutes 753 --json
python -m living_world scenario smelting --seed 8 --minutes 754 --json
python -m living_world scenario smelting --seed 8 --days 1 --json
```

All 54 tests passed in the installed Windows environment. Tests cover purchases with finite stock and funds, exact payments to suppliers, charcoal in transit, both input shortages, cancellation and retry, saved batches, and full inventory reconciliation. The mining scenario retained its seed-8 digest.

In seed 8, the smelter bought ore from the miner at minutes 232 and 241 and charcoal from the burner at minute 542. Those sales paid the miner four coins and the burner five. The first batch finished at minute 754. A saved run advanced through minutes 753 and 754 and then to the end of day one matched the direct runs.

A batch of 60 independent runs used seeds 0–9 at horizons of 1, 7, 30, and 90 days with both inputs available, plus seven-day cases with an empty ore deposit or an empty woodland. It took about 28.3 seconds. Grain, seed, standing wood, firewood, ore, charcoal, iron, and the 114-coin supply reconciled in every run. All baseline runs reached four units of iron by day seven. All shortage runs produced zero iron. The available supplier was still paid in both shortage cases.

### Remaining Phase 1 work

Iron currently accumulates at the smeltery. The smelter targets four units and starts with 42 coins. The next slice adds a blacksmith who buys iron and uses it to make tools.

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
