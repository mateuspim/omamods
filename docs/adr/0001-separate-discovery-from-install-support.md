# 1. Separate game discovery from install support

- Status: Accepted
- Documented: 2026-10-20

## Context

A game can be visible in Steam or Heroic before OmaMods knows how to install
its mods. A catalog manifest can identify its Steam app ID and note a likely
adapter without proving archive compatibility.

## Decision

`games/<id>/game.yml` is discovery metadata. The validated `adapter` field
names a workflow family. Installer definitions and detected game layouts
separately determine whether the TUI labels a game mod-ready. Read-only
`game list` and `inspect` use catalog and local install metadata only.

## Consequences

- The shelf can show catalog games and other installed games without offering
  unsupported writes.
- A new manifest needs no installer, but it must not be described as one.
- Adding install support requires a planner, tests, and game-specific docs.

See `src/omamods/manifests.py`, `src/omamods/game_shelf.py`, and
`src/omamods/pak_games.py`.
