# ADR 0008 — Iron purchases and basic forging

**Status** Accepted.

Use the existing timed delivery path to move iron from the smeltery to a stall. The blacksmith buys at the square with a funded purchase that credits the smelter. The price of 12 coins covers the nine-coin ore and charcoal cost in the current smelting recipe.

A forging job requires the blacksmith at the forge. It reserves one iron unit and converts it into one iron hoe on completion. The same inventory and action rules handle cancellations, saved jobs, and retries.

Model hoes as counted goods with a three-unit forge stock target while farm demand is being introduced. The recipe and duration are simulation rules. A later slice will account for purchases, use, and wear.
