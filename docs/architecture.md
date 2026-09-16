# Architecture

OmaMods owns the reproducible description of a mod setup. A game-specific
manager, when one exists, remains responsible for the format it understands.

```text
Git repository                 Persistent host storage              Distrobox
----------------              -----------------------              ---------
game adapters                 downloaded mod archives              mod tools
profiles and install rules    backups and state snapshots           Proton helpers
checksums and source URLs     optional persistent manager data      runtime deps
          \                         |                                /
           \-------------------- OmaMods --------------------------/
                            inspect / apply / revert
```

## Adapter kinds

| Kind | OmaMods action |
| --- | --- |
| Direct overlay | Copy declared files, set loader options, track ownership, revert. |
| External manager | Install or launch the established manager in the correct environment. |
| Archive patcher | Stage sources and tool, create a backup, guide the necessary GUI step. |
| Game-native manager | Preserve sources and launch the game manager; do not edit undocumented state. |

## Persistent layout

The default storage root will be configurable. It must be outside the
container so a deleted Distrobox never deletes the source archives or backups.

```text
<storage-root>/
  archives/<game>/
  backups/<game>/<timestamp>/
  state/<game>/<profile>.json
```

## First implementation boundary

Start with a CLI that reads one game manifest and can run read-only discovery.
The first write-capable feature should be a direct-overlay adapter with a
backup and revert path. A TUI can call the same core later.
