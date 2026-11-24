# ADR 0002 — Standing grain offers

**Status** Accepted.

Each farm's standing offer derives from available grain above a household reserve. Small offers have a higher asking price. Buyers choose among local offers and the authoritative simulation rechecks the chosen quote when it accepts the sale.

A pending purchase persists its seller and accepted price. The pending action reserves both the grain and the coins, so later changes in available stock affect new quotes and leave existing agreements at their accepted prices. Offers themselves are recalculated from inventory and pending actions on inspection or purchase.

This models finite stock, competing suppliers, price response, and settlement through the existing transaction mechanism. Negotiated prices and individual order books can build on this once transport or trade volume gives them a gameplay purpose.
