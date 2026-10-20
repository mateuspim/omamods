# Profile workflow proposal

**Status: proposed.** General versioned profiles, whole-game backups, external
manager launching, and Distrobox orchestration are not implemented. Current
write-capable workflows install supported archives and maintain ownership
records for those files. The [architecture](../architecture.md) describes that
implemented boundary.

The original project goal is a reproducible game-mod profile with the declared
mod sources and install rules in Git, and downloaded archives, backups, and
mutable state in persistent host storage. A deleted Distrobox should not erase
the source material needed to rebuild or revert a profile. A game-specific
manager should remain responsible for formats it already understands.

A future profile command may resemble:

```text
omamods profile apply dawnwalker/default
omamods profile revert dawnwalker/default
omamods manager open <game>
```

Before enabling these commands, the design needs a versioned profile schema,
preflight of game and archive versions, backup and restore semantics across all
adapter kinds, interruption recovery, and tests that prove a complete revert.
Do not infer those features from a `game.yml` manifest or the existing
per-file records.
