# ADR 0005 — Purchased fuel and timed charcoal batches

**Status** Accepted.

Use the existing stall and firewood purchase for the kiln buyer. Settlement debits the buyer's wallet and credits the woodcutter. Each purchase competes with household demand for the same available bundles.

The burner carries the bundles to the kiln. Starting a batch reserves two bundles in the burner's inventory. On successful completion the transaction consumes both bundles and credits one charcoal unit to the fixed kiln stock. Canceling releases the input hold. The existing action queue persists the batch and its finish time.

Use a four-unit stock target for the burner until a charcoal buyer is introduced. The burner can take existing farm shifts to earn food money. The recipe, time, and stock target are scenario rules for the simulation.
