# 0012 — Hamlet employment and configurable farms

## Decision

New `hamlet` saves use `village-hamlet-2`. The default remains two farms and 31 residents. A configuration selects up to four additional sites from an ordered catalog of farm owners, fields and road durations. Additional farms have independent funded accounts and the same rules for food, wages, tools and seed.

The forge has an input account at its workshop. The blacksmith unloads one unit of iron after buying it and traveling back. The blacksmith can use that iron directly or pay an eligible farmhand to do the shift. One shift runs at a time and a hired shift reserves iron and the wage at submission. Loss of a worker during a shift cancels it and releases both reservations.

## Consequences

A farmhand can earn money in the workshop and a craft worker can earn field wages while their trade or supplies stall. Both jobs use the same action queue, needs rules and accounting. Older scenarios retain their original content versions and forge input rules.
