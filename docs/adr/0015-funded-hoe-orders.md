# 0015 — Funded hoe orders at the market square

## Decision

The `contracts` scenario retains the civilian rules for production and owns its order policy. A farm that needs a hoe can fund one order with a 19-coin transfer into its escrow. It requests one hoe of quality 40 or higher. The board shows the deadline and assignment. Acceptance reserves the assignment while the action is pending. Ada can claim the order when backed by her stall stock.

An assigned supplier submits a qualifying item at the market square. The item reservation identifies the exact tracked hoe. Its transfer to the farm's pickup stock and the supplier's payment commit together. The farmer collects the hoe at the square and can install it at the field as usual.

## Consequences

The exclusive deadline is two days from posting. An open or accepted order expires at that minute and refunds its full escrow. Closed orders stay in the save for inspection. Inventory audit verifies that every farm has at most one active order and the correct balance in escrow.
