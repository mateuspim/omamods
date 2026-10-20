# 6. Rename containers to choose Unreal load order

- Status: Accepted
- Documented: 2026-10-20

## Context

[ADR 5](0005-predict-unreal-asset-load-order.md) predicts which of two
colliding Unreal containers the game shows, but users could not change the
outcome. In a real case, a mod for MGS Delta ships
`~mods/Outfit_P` and a separate `~mods/Fix_P` that the author says to
install with it. Both carry the same physics asset, and by name order
`Outfit_P` wins, so the fix probably never applies.

Unreal has no load-order file for these mods: it derives mount priority from
the container's file name. The only lever is the name.

## Decision

On request (`P` or `:load-last` on an installed file), rename each of the
file's containers that loses a collision to `<base>_<n>_P`, where `<base>` is
the name without its patch suffix and `n` is the highest rank among the
containers it collides with (at least 1). Since `_<n>_P` ranks n + 1, the new
name wins by number alone, whatever the other mods are called. A `z_` prefix
was rejected because its outcome depends on the other names. The base name
stays, so the file is still recognisable in the Paks folder.

All files of a container (`.pak`, `.utoc`, `.ucas`) are renamed together, and
the file's ownership record is rewritten atomically with the new
`relative_path`s. The digests and `archive_sha256` stay, because a rename does
not change bytes, so revert still checks and removes every file. Before
renaming, each owned file must still match its recorded SHA-256 and no new
name may exist. A failed rename moves already-renamed files back. Games that
do not load Unreal paks by name (RE Engine patch chains, REDengine, and ASI
loader games) are refused.

The choice is stored beside the record as `<record>.load-order`, mapping the
archive's container stem to the chosen stem. It survives revert, and every
install of the same file (and variant) applies it when planning targets, so
reinstalling or updating keeps the priority. `:load-default` renames back to
the archive's names and removes the entry.

## Consequences

- Users can make a mod win a collision without editing files by hand, and
  undo it.
- IoStore containers (`.utoc`/`.ucas` with a stub `.pak`) are renamed on the
  belief that the engine derives their mount order from the file name, as it
  does for `.pak`. This is standard practice for UE5 mods but is not verified
  per game; a game that orders containers itself can ignore the rename.
- The choice belongs to a file ID. An update published as a new Nexus file ID
  starts from the archive's names again.
- The install confirmation's target list shows the archive's names, while
  its collision warning and the installed files use the chosen ones.

See `src/omamods/load_priority.py`, `src/omamods/container_rename.py`,
`src/omamods/load_order_store.py`, and `src/omamods/tui/load_order_choices.py`.
