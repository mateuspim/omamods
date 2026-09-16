# OmaMods

OmaMods is an Arch-first tool for reproducible game-mod profiles.

It coordinates Steam, Proton, Distrobox and the mod tools that games already
use. It does not try to replace every game-specific mod manager.

## First target

The Blood of Dawnwalker is the first game adapter. Its initial job is to prove
the workflow: discover a Steam game, preserve mod archives outside a Distrobox,
record a versioned profile, apply it safely, and restore the original state.

## Project principles

- Keep manifests, install rules and profiles in Git.
- Keep downloaded archives and backups in persistent host storage.
- Treat each game as an adapter: direct overlay, external manager, archive
  patcher, or a game-native manager.
- Verify game versions and archive contents before applying a profile.
- Make every managed change reversible.

## Planned commands

```text
omamods game list
omamods inspect dawnwalker
omamods profile apply dawnwalker/default
omamods profile revert dawnwalker/default
omamods manager open <game>
```

See [the architecture](docs/architecture.md) and the
[Dawnwalker adapter](games/dawnwalker/README.md).
