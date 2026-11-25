# Living World

Living World is a local, text-based fantasy MUD under development. The prototype runs a deterministic simulation from the command line. In the `seed-saving` scenario, farmers buy and replace iron hoes and set aside part of the harvest for the next planting.

## Run locally

Use Python 3.12 or newer. The simulation itself uses only the standard library.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m living_world scenario village --seed 42 --days 7 --json
```

On macOS and Linux, use `.venv/bin/python`. To run directly from the source tree without installing packages, set `PYTHONPATH=src` in your shell (`$env:PYTHONPATH = "src"` in PowerShell), then use `python -m living_world`.

## Run a 31-person hamlet

The `hamlet` scenario runs the full seed-trade village with 24 farmhands instead of two. Each farm can pay up to six hired harvest shifts at once.

```powershell
.\.venv\Scripts\living-world.exe scenario hamlet --seed 8 --days 7 --json
```

Check `village.needs` for hunger and `village.employment` for paid forge shifts and craft workers taking field jobs. The default village has 222 coins. To add farms and jobs, pass a JSON file such as `{"hamlet":{"farms":4,"farmhands":32,"hired_shifts_per_farm":8}}` with `--config`.

## Export the Phase 1 viability report

1. From the project folder, create the output folder and run the baseline. This starts ten independent villages and checks them on days 1, 7, 30 and 90. The report can take several minutes.

   ```powershell
   New-Item -ItemType Directory -Path saves -Force | Out-Null
   .\.venv\Scripts\living-world.exe report hamlet --seeds 0-9 --days '1,7,30,90' --json |
       Set-Content -Encoding ascii saves/hamlet-phase1-baseline.json
   ```

2. Read the number of functional villages. Each run checks the last week's production, food purchases and meals, the final grain stock, hunger, failed actions and the ledger. The Phase 1 target is at least nine of ten functional villages at day 90.

   ```powershell
   Get-Content -Raw saves/hamlet-phase1-baseline.json |
       ConvertFrom-Json | Select-Object functional_seeds, seed_count, runtime_seconds
   ```

3. To reproduce a shorter disruption, use `report hamlet --seeds 0,8,9 --days 1,7` with `--shock seed-shortage` or `--shock worker-loss`. For a village that starts with an empty deposit or woodland, use `--config` with a JSON file containing `{"starting_ore_deposit":0}` or `{"starting_standing_wood":0}`.

## Compare a week with and without saving seed

1. In PowerShell, from the project folder, create two configuration files. Both give each farm one seed to start. The first sets a target of four seeds per farm. The second sets the target to zero and disables seed saving.

   ```powershell
   New-Item -ItemType Directory -Path saves -Force | Out-Null
   '{"village":{"starting_seed":1,"seed_reserve_target":4}}' | Set-Content saves/low-seed-saving.json
   '{"village":{"starting_seed":1,"seed_reserve_target":0}}' | Set-Content saves/low-seed-control.json
   ```

2. Run both versions of the same seven-day simulation.

   ```powershell
   .\.venv\Scripts\living-world.exe scenario seed-saving --seed 8 --days 7 --config saves/low-seed-saving.json --json
   .\.venv\Scripts\living-world.exe scenario seed-saving --seed 8 --days 7 --config saves/low-seed-control.json --json
   ```

3. Compare `village.seed_saving.seed_by_farm` and `village.grain_eaten`. With seed saving, each farm ends with four seeds and residents eat 180 grain. With seed saving disabled, both farms run out of seed after two harvests and residents eat 15 grain.

## Watch a farm buy seed after a shortage

1. From the project folder, run the first command alongside the second for a comparison. Both remove the east farm's unreserved seed at the end of day one.

   ```powershell
   .\.venv\Scripts\living-world.exe scenario seed-trade --seed 8 --days 7 --shock seed-shortage --json
   .\.venv\Scripts\living-world.exe scenario seed-saving --seed 8 --days 7 --shock seed-shortage --json
   ```

2. In the first result, `village.seed_trade` shows one seed bought and unloaded for two coins. Under `village.seed_saving.seed_by_farm`, the east farm ends with four seeds. Its reserve reaches zero in the second run.

## Watch farming tools pay off and wear out

From the project folder in PowerShell, run these commands one at a time.

```powershell
(.\.venv\Scripts\living-world.exe scenario tools --seed 8 --days 1 --json | ConvertFrom-Json).village.tools
(.\.venv\Scripts\living-world.exe scenario tools --seed 8 --days 7 --json | ConvertFrom-Json).village.tools
```

On day one, the first farm paid **15 coins** for a hoe, installed it, and grew **2 extra grain** on the first assisted harvest. By day seven, `assisted_harvests` is **29**, `bonus_grain` is **58**, and `replacement_hoes_installed` is **3**. Each hoe lasts eight assisted harvests.

Use `create --scenario tools` to keep a world and `inspect --journal` to see purchases, installation, assisted harvests, and wear.

## Watch the first iron hoe finish

From the project folder in PowerShell, run these commands one at a time.

```powershell
(.\.venv\Scripts\living-world.exe scenario blacksmith --seed 8 --minutes 1039 --json | ConvertFrom-Json).village.blacksmith
(.\.venv\Scripts\living-world.exe scenario blacksmith --seed 8 --minutes 1040 --json | ConvertFrom-Json).village.blacksmith
```

At minute 1039, the blacksmith has paid the smelter **12 coins** and the first hoe is in progress. At minute 1040, `iron_consumed` and `hoes_in_stock` both show **1**.

Use `create --scenario blacksmith` to keep the world and `inspect --journal` to see deliveries, payments, and forging as separate transactions. With a JSON config that sets `starting_ore_deposit` to zero, the forge waits for iron.

## Watch the first iron batch finish

From the project folder in PowerShell, run these commands one at a time.

```powershell
(.\.venv\Scripts\living-world.exe scenario smelting --seed 8 --minutes 753 --json | ConvertFrom-Json).village.smelting
(.\.venv\Scripts\living-world.exe scenario smelting --seed 8 --minutes 754 --json | ConvertFrom-Json).village.smelting
```

At minute 753, the smelter has paid the miner **4 coins** and the charcoal burner **5 coins**. The first batch is in progress and `iron_in_stock` is **0**. At minute 754, the report shows **2 ore consumed**, **1 charcoal consumed**, and **1 iron in stock**.

Use `create --scenario smelting` to keep a world and `inspect --journal` to see the payments and production transactions. For a shortage run, pass a JSON config with `starting_ore_deposit` or `starting_standing_wood` set to zero.

## Watch iron ore reach the market

From the project folder in PowerShell, run the commands one at a time.

```powershell
(.\.venv\Scripts\living-world.exe scenario mining --seed 8 --minutes 158 --json | ConvertFrom-Json).village.mining
(.\.venv\Scripts\living-world.exe scenario mining --seed 8 --minutes 159 --json | ConvertFrom-Json).village.mining
```

At minute 158, `delivery_arrives_at` is **159** and `ore_at_market` is **0**. At minute 159, `ore_at_market` is **3** and `ore_at_mine` is **0**. By the end of day one there are six units of ore at the stall and 114 in the deposit.

The deposit starts at 120 units. A scenario config can set `starting_ore_deposit` to a smaller number or zero. Use `create --scenario mining` to keep a world and `inspect --journal` to see extraction and transport as separate transactions.

## Watch the first charcoal batch finish

From the project folder in PowerShell, run the commands one at a time.

```powershell
(.\.venv\Scripts\living-world.exe scenario charcoal --seed 8 --minutes 350 --json | ConvertFrom-Json).village.charcoal
(.\.venv\Scripts\living-world.exe scenario charcoal --seed 8 --minutes 440 --json | ConvertFrom-Json).village.charcoal
```

At minute 350, `batch_finishes_at` shows **437** and `charcoal_in_stock` is **0**. At minute 440, `firewood_used_at_kiln` is **2** and `charcoal_in_stock` is **1**. Both runs report firewood purchases by the kiln and by households.

Run with `--days 1` for the full first day. In this seed the kiln buys eight bundles and makes four batches. Households buy two bundles from the same stall. Use `create --scenario charcoal` to keep a world and `inspect --journal` to read its transactions.

## Watch firewood reach the market and heat the farmhouses

From the project folder in PowerShell, run these commands one at a time. They display the forestry part of the report.

```powershell
(.\.venv\Scripts\living-world.exe scenario firewood --seed 8 --minutes 125 --json | ConvertFrom-Json).village.forestry
(.\.venv\Scripts\living-world.exe scenario firewood --seed 8 --days 1 --json | ConvertFrom-Json).village.forestry
```

At minute 125, `firewood_delivered` shows **3** and the stall charges two coins per bundle. After one day, `firewood_sold` and `firewood_burned` both show **2**, and `heated_rests` shows **4**. Cutting, hauling, buying, and burning each have a distinct journal entry. Use `create --scenario firewood` to keep a world and `inspect --journal` to read its transactions.

The woodland starts with 240 units of standing wood. To test depletion, a scenario config can set `starting_standing_wood` to a smaller number or zero.

## Watch grain arrive at the market

From the project folder in PowerShell, run the commands one at a time.

```powershell
.\.venv\Scripts\living-world.exe scenario routes --seed 8 --minutes 50 --json
.\.venv\Scripts\living-world.exe scenario routes --seed 8 --minutes 70 --json
```

At minute 50, the east farm is the only seller under `village` → `market` → `offers`. The west farmer is carrying three grain and will arrive at minute 65. At minute 70 both farms have grain for sale. Each command starts the same seeded scenario and stops at the specified minute.

Use `--days 7` in place of `--minutes 70` for a full week. The `travel` section reports completed trips, delivered grain, and any trips still in progress. The `routes` scenario also accepts both market shocks described below.

## Compare a normal week and a seed shortage

From the project folder in PowerShell, run these commands one at a time in the installed environment.

```powershell
.\.venv\Scripts\living-world.exe scenario market --seed 8 --days 7 --json
.\.venv\Scripts\living-world.exe scenario market --seed 8 --days 7 --shock seed-shortage --json
```

Look under `village` → `market`. In the first run, the west farm makes 14 sales and every sale costs one coin. In the second, the other farm loses its unreserved seed after day one. The west farm makes 45 sales, and one sale costs two coins.

For a second experiment, use `--shock worker-loss`. After day one, one farmhand loses the ability to do field work and remains part of the village. To keep a world between commands, use `create --scenario market` or `create --scenario routes`, then advance it with the save commands below.

## Save and inspect a village

```sh
python -m living_world create --scenario village --seed 42 --save saves/alderwick.db
python -m living_world simulate --save saves/alderwick.db --days 7 --headless
python -m living_world inspect --save saves/alderwick.db --summary
python -m living_world inspect --save saves/alderwick.db --journal
```

Replace `python` with the virtual environment's interpreter if it is not on your path. The `simulate` command also accepts `--minutes`. A stopped process leaves the world at its last committed simulation minute. The next run resumes pending work and NPC decisions from that point. The summary reports stocks, money, needs, and completed activities. The journal shows the source, destination, and preceding event for each committed resource movement.

## Run a controlled scenario

```sh
python -m living_world scenario lab --seed 42 --json
python -m living_world scenario village --seed 42 --days 7 --config saves/shortage.json --json
```

The lab schedules one grain delivery and reports the resulting state and journal. Save the following JSON as `saves/shortage.json` for the shortage comparison.

```json
{"village": {"starting_seed": 0}}
```

The `scenario` command uses temporary saves. `create` and `scenario` accept the same JSON configuration overrides. The config is validated and stored with the world at creation. For manual lab tests, `create` defaults to the lab, and `transfer --save ... --id ... --actor storekeeper --target neighbor --quantity 2 --duration 10` schedules a delivery. Submitting the same action ID and parameters returns the original action. Run `python -m living_world --help` for all commands.

## Tests

```sh
python -m pip install -e ".[test]"
python -m pytest -q
```

The same tests can run offline. Set `PYTHONPATH=src` as above and run `python -m unittest discover -s tests -v`.

See [Architecture](docs/ARCHITECTURE.md), [Roadmap](docs/ROADMAP.md), and [Progress](docs/PROGRESS.md).
