# ADR 0007 — Industrial purchases and smelting

**Status** Accepted.

Use funded market purchases from the miner's ore stall and the charcoal burner's delivered stock. Keep prices fixed for this slice at two coins per ore and five per charcoal. The charcoal price covers the burner’s four-coin firewood cost per unit in the current recipes. Both purchases debit the buyer and credit the corresponding supplier.

A smelting batch starts only at the smeltery with both inputs available. Before scheduling, the simulation checks the complete set of required inputs and then reserves them together. Successful completion consumes two ore and one charcoal and creates one iron in the smeltery stock. Cancellation releases both holds.

Use a four-unit production target while iron accumulates for a future forge. The recipe and durations are gameplay rules. A later blacksmith gives the smelter a customer and replenishes the smelter's working funds.
