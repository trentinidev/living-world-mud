# Living World

Living World is a local, text-based fantasy MUD under development. The prototype runs a deterministic simulation from the command line. In the `mining` scenario, a miner works a finite deposit and delivers iron ore to the village market.

## Run locally

Use Python 3.12 or newer. The simulation itself uses only the standard library.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m living_world scenario village --seed 42 --days 7 --json
```

On macOS and Linux, use `.venv/bin/python`. To run directly from the source tree without installing packages, set `PYTHONPATH=src` in your shell (`$env:PYTHONPATH = "src"` in PowerShell), then use `python -m living_world`.

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
