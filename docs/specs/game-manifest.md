# Game manifest specification

Each catalog game has `games/<id>/game.yml`. `manifests.py` validates every
field before discovery. The directory name must equal `id`. A manifest makes a
game discoverable; it does not turn on an installer.

```yaml
id: dawnwalker
name: The Blood of Dawnwalker
status: discovery
platforms:
  - steam
adapter: direct-overlay
steam_app_id: 3751260
notes:
  - Loader-based mods need separate support.
```

| Field | Shape | Meaning |
| --- | --- | --- |
| `id` | Required lowercase slug, digits and internal hyphens allowed | Stable catalog ID and containing directory name. |
| `name` | Required nonempty string | Display name. |
| `status` | `discovery` or `ready` | Catalog status, separate from actual installer support. |
| `platforms` | Exactly `[steam]` | Discovery platform supported by this schema. |
| `adapter` | `undecided`, `direct-overlay`, `external-manager`, `archive-patcher`, or `game-native` | Proposed workflow family. |
| `steam_app_id` | Positive integer or null | Exact Steam match when configured. |
| `notes` | Optional list of nonempty strings | Game-specific constraints and provenance. |

The `adapter` values describe the workflow a game is expected to need once
install support exists:

| Adapter | Intended workflow |
| --- | --- |
| `undecided` | Not yet researched. |
| `direct-overlay` | Copy declared files, set loader options, track ownership, revert. |
| `external-manager` | Install or launch the established manager in the correct environment. |
| `archive-patcher` | Stage sources and tool, create a backup, guide the necessary GUI step. |
| `game-native` | Preserve sources and launch the game's manager; do not edit undocumented state. |

Unknown fields, duplicate YAML keys, unsafe YAML tags, a mismatched directory
name, and values outside these shapes are rejected. `steam_app_id: null`
means Steam matching is not configured. A Steam build ID found during
inspection is metadata, not a verified executable version.

`omamods game list` loads the catalog and reports local installation status.
`omamods inspect <id>` shows discovery details. The commands do not change
Steam, Proton, or game files. Installer support must be implemented and tested
separately; see [architecture](../architecture.md) and the
[game workflows](../game-workflows.md).
