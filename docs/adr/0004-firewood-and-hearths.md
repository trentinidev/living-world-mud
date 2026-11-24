# ADR 0004 — Firewood extraction and heat

**Status** Accepted.

Model standing wood and cut firewood as separate goods. A cutting job removes units from the woodland account and produces the same number of bundles in the woodpile. Transport and purchases reuse reservations and commit resource movements on completion. This exposes depletion, lost time, and budget shortages to the same ledger checks as grain.

Use hearth heat as the first source of demand. Each completed burn consumes one bundle and sets a warmth expiry at the farm. Temperature is represented by warm or cold at rest completion. Use a fixed two-coin bundle price and a finite woodland stock to isolate the initial supply chain. Regrowth, seasonal thermal demand, and industrial buyers can build on the same accounts and actions.
