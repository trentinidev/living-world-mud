# ADR 0009 — Installed farm tools and wear

**Status** Accepted.

Deliver hoes from the forge to the market stall. A farmer pays the blacksmith and brings the hoe home. Installing it moves the item from the farmer's inventory to the farm's pantry and records eight available uses for that farm.

A pending assisted harvest reserves exclusive use of the farm's installed hoe. The reservation is derived from its saved action. On completion, add two grain to the seeded base yield and spend one use. Consume the physical hoe and record the retirement on the final use. The base harvest remains available when a tool is absent.

The first implementation uses one active hoe per farm, a fixed 15-coin price, a fixed wear rate, and an expiry recorded in the same transaction as the harvest. Replacement demand feeds sales back to the forge.
