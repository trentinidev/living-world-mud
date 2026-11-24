# ADR 0001 — Transactional SQLite snapshot and journal

**Status** Accepted.

Use one local SQLite save per world. Use a pure Python discrete-event core and a SQLite adapter. Store a canonical world snapshot and append the events from each mutation in the same transaction. SQLite's writer lock serializes mutations on the same save.

This keeps save/load, causal inspection, and retry behavior testable as the simulator grows. Pending actions carry enough information to reconstruct holds from their immutable intents, current rules and save configuration. The journal links outcomes to starts and records movement boundaries for production and consumption.

The implementation rewrites the snapshot on each successful write and retains action and journal history. This is suitable for the current farmstead. Profile long runs and larger actor counts before changing storage layout or retention.
