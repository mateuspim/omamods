# 5. Predict Unreal asset load order from container names

- Status: Accepted
- Documented: 2026-10-20

## Context

Unreal mods replace game assets by shipping packages at the same path inside
their own `.pak` or IoStore `.utoc`/`.ucas` container. Two installed mods can
carry the same package without writing the same file, so the ownership check
from [ADR 2](0002-record-ownership-for-revert.md) cannot see the clash, and
only one mod's version shows in game. Users need to know which one.

## Decision

Read the directory index of each installed (or planned) `.utoc` and `.pak`,
using ranged reads so multi-gigabyte paks load only their footer and index.
Key entries by package path (ignoring `.uasset`/`.uexp`/`.ubulk` and case) and
skip the `Label_*` PrimaryAssetLabel that mod kits add to every mod. Report
every shared package between two containers, including two files of one mod.

Predict the winner from the engine's pak order: `_P` patch containers outrank
plain ones, a `_<n>_P` suffix with n >= 1 ranks n + 1, and equal ranks go to
the name that sorts later, ignoring case, since the engine mounts in
descending name order and the first-mounted container answers lookups.

## Consequences

- Collisions show in the inspector and the install confirmation. They are
  warnings: installs are never blocked by them.
- The order is a prediction from engine defaults recalled without a game
  test. A game that mounts containers itself, or a loader that reorders them,
  can differ, so the UI says "likely".
- Encrypted or signed indexes are listed as "not checked" instead of guessed.
- Index readers support `.utoc` version 5 layouts and `.pak` versions 3-11;
  new layouts need a fixture in `tests/pak_builders.py`.

See `src/omamods/asset_collisions.py`, `src/omamods/iostore_index.py`,
`src/omamods/pak_index.py`, and `src/omamods/tui/asset_conflicts.py`.
