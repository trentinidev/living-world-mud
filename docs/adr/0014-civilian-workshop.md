# 0014 — Civilian workshop and tool ownership

## Decision

New `civilian` saves use the hamlet's locations, people and economy. The same forge validates access to an anvil, time, a shared slot and two physical inputs. Employees craft from the workshop accounts and earn wages. Renters craft from personal stock, pay one coin to the workshop owner and keep the output.

One completed hoe grants one experience point. Ada starts with nine points. Rank rises every three points up to rank five. A higher rank increases the quality score and narrows its random range. Fatigue lowers the score. Each item record stores its maker, quality, immediate material accounts and remaining uses. Future material grading can build on that record.

Ada pays 16 coins per hoe when the stall needs stock. The three costs for one independent hoe total 15 coins. Her stall price is 18 coins in the civilian scenario to cover iron, fuel and possible hired labor. A transaction reserves the actual payment and inventory.

## Consequences

The independent smith has room for a one-coin margin when iron, fuel and a buyer are available. Shop demand and cash can prevent a sale. Quality is recorded through the life of the hoe and the standing sale currently uses a fixed price.
