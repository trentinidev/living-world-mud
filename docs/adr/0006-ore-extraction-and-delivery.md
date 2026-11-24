# ADR 0006 — Finite ore and market deliveries

**Status** Accepted.

Represent unextracted ore, mined ore, and delivered ore through separate inventory accounts. Each completed mining shift debits the finite deposit and credits the same number of iron ore units at the mine. The miner can take a smaller shift when the remaining deposit is below the normal yield.

Use the shared timed travel action for ore deliveries. Cargo holds reserve mine stock and release on cancellation. Completion atomically moves the miner and brings the reserved ore into the stall.

Use a six-unit stock target to limit extraction while the stall builds inventory for the first smelter. The miner can take existing farm shifts for food money.
