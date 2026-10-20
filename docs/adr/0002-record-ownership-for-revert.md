# 2. Record file ownership for safe revert

- Status: Accepted
- Documented: 2026-10-20

## Context

Mods write into game directories shared with the game, updates, and other
mods. A filename alone cannot show whether OmaMods may later remove it.
Some supported workflows also replace an empty patch or set aside a prefix
configuration file.

## Decision

Preflight planned targets before writing. Store per-file or per-variant JSON
records with target paths, archive identity, and hashes. Refuse collisions
with unrelated files. On revert, use the record and verify modified targets
where applicable; restore originals that were explicitly set aside. Keep
reading older one-record-per-mod state for compatibility.

## Consequences

- A changed file can stop revert instead of being silently removed.
- Staging and state must be retained together with the game files.
- Each new installer needs collision, partial failure, and revert tests.

See `src/omamods/pak_storage.py`, `src/omamods/install_records.py`, and
`src/omamods/original_files.py`.
