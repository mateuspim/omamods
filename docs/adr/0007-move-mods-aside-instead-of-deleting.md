# 7. Move mods aside instead of deleting them in library clean-ups

- Status: Accepted
- Documented: 2026-11-04

## Context

Uninstalling one mod (`u`, `U`) deletes the files its record owns, which is
safe: the archive stays in staging and installs again. Library-wide clean-ups
are different. `X` handles files with no record, so OmaMods has no archive to
reinstall them from, and the scan can flag a file the game needs (an RE Engine
patch looks like a mod's). `C` resets every game, including mods whose staged
archives may be gone, and a file the user edited after installing makes
revert refuse.

## Decision

Library clean-ups never delete a mod file. Each run gets a dated
`removed/<stamp>/` folder in the storage root. Unrecorded files move into its
`untracked/` folder. Recorded files are hard-linked, or copied across drives,
into its `tracked/` folder before their records revert them. A file that
changed since install is then removed anyway, because its copy is already
kept. Each folder has a `moved.json` that maps the kept file to its original
path. Folders left empty are removed, except the game's install folder, its
Paks folder, and the folders Cyberpunk ships.

## Consequences

- Any clean-up can be undone by hand from `moved.json`, and an edited file is
  not lost.
- Copies across drives cost disk space until the user deletes the dated
  folder. OmaMods does not prune `removed/`.
- The scan looks only in folders the game does not ship, so it can miss a mod
  that overwrote a game file in place. The confirmation tells the user to
  verify the game's files in Steam if it misbehaves.
