# 0013 — Local player commands use the existing simulation

## Decision

An optional player ID in a hamlet save marks one actor as manually controlled. The character starts at the east farm with the configured farmhand allowance. Its stock appears in the world initialization event and contributes to the save's coin supply from minute zero. World snapshots without a player omit the optional ID.

Read commands open a read-only save transaction. Time-consuming commands submit existing intents and advance the world through completion in a write transaction. NPCs use the same event queue during that time. The CLI gives the player the committed result before reading the next command.

## Consequences

Leaving the prompt open leaves game time unchanged. Closing and reopening the program resumes the authoritative save. The interface currently supports one local civilian and paid field work. Workshop progression will use the same action path.
