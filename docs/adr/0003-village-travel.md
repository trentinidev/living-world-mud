# ADR 0003 — Timed village travel and fixed storage

**Status** Accepted.

Use a new content version for the village with roads. Keep actor positions at the last completed site and persist any trip in the existing action queue. The topology and durations come from the versioned scenario. Both farm sites connect to a common square.

Reserve a delivery against the source pantry for the duration of the trip. Set the actor's destination and move the reserved goods to the stall in the same completion transaction. This keeps cargo unavailable for sale while a trip is pending and makes cancellation release the reservation without a second inventory movement.

Harvests produce into field pantries. Stalls sell only grain already delivered to the square. The owner authorizes these standing offers by delivering stock. A field owner can sell through a stall while field work continues at the farm. The prototype uses fixed roads and resolves interruptions at the last completed site.
