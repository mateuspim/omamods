# Architecture

OmaMods has three paths through one Python package: read-only discovery, a
Textual workspace, and narrow write-capable installers. The catalog describes
games; installer definitions and archive planners decide whether a game is
mod-ready. The two are deliberately separate.

```text
Steam + Heroic ──> discovery ──> game shelf ──> Textual screens
                       │                             │
 games/<id>/game.yml ──┘                        ModsService
                                                    │
       Nexus / Ayaka / releases ──> staging ──> archive plan
                                                    │
                                      preflight ──> game files
                                                    │
                                   ownership record ──> revert
```

## Entry points and boundaries

| Area | Implementation | Responsibility |
| --- | --- | --- |
| CLI | `cli.py`, `__main__.py` | Parse commands and select read-only or write-capable workflows. |
| Discovery | `manifests.py`, `steam_libraries.py`, `steam_apps.py`, `shelf_scan.py`, `heroic_games.py` | Validate catalog entries and locate local installations. |
| TUI | `tui/app.py`, `tui/games_screen.py`, `tui/mods_screen.py`, `tui/downloads_screen.py` | Present state and dispatch user actions. |
| Service boundary | `tui/service.py`, `host_cli.py` | Inject host paths, transport, archive reader, browser, Steam, and theme adapters. |
| Site integrations | `nexus_api.py`, `ayaka_pages.py`, `release_api.py`, `mod_fetch.py` | Obtain metadata and downloads, then stage them. |
| Install planning | `asset_plans.py`, `pak_archive.py`, `red_archive.py`, `re_pak_archive.py`, `asi_archive.py`, `ue4ss_archive.py` | Recognize supported layouts and name target paths. |
| Apply and revert | `pak_storage.py`, `install_records.py`, `original_files.py` | Preflight targets, write files, record hashes, and restore or remove owned files. |

The `game list` and `inspect` commands read manifests and Steam metadata. They
neither install mods nor mutate a game. The TUI starts with a shelf scan that
combines catalog games with Steam and Heroic installations. Catalog Steam games
match by app ID, not by a similar display title. Installed Unreal and RE Engine
games can become mod-ready after layout detection and a Nexus game match.

`games/<id>/game.yml` is a discovery declaration. Its `adapter` value names a
proposed family, not a promise that an installer works. The exact schema is in
[the manifest spec](specs/game-manifest.md). Installer definitions live in
`pak_games.py` and detected games in `pak_detection.py` and
`re_engine_detection.py`.

## Download and installation flow

1. The selected site supplies metadata and an authorized download link, or the
   user supplies an archive. Files are staged under the configured host storage
   root. The private key or login cookie stays in the user config.
2. The planner reads archive members and offers variants when needed. It
   rejects unsupported layouts and maps accepted members to target paths.
3. Apply checks target paths and ownership before writing. Existing unowned
   files are generally refused. Documented exceptions, such as a Proton prefix
   `Engine.ini` or an empty RE Engine patch, preserve their original state.
4. Each installed file or variant gets a JSON ownership record with its target
   paths and SHA-256 hashes. Revert uses the record, refuses to remove a changed
   file where applicable, and restores originals that were set aside.

The CLI's `nexus install`, `sync`, and `revert` use the same installer core for
configured games. A browser's `nxm://` invocation runs as a separate process;
it writes staged content and download status where the TUI can find it.

## Host storage

By default, private settings are in `~/.config/omamods/config.toml` and
persistent content in `~/.local/share/omamods`. XDG overrides and `[storage]
root` can change those locations. The important paths are:

```text
<storage-root>/
  archives/<game>/<mod-id>/mod.json
  archives/<game>/<mod-id>/<file-id>/<archive>
  state/<game>/<mod-id>/<file-id>.json
  state/<game>/<mod-id>/<file-id>.<variant-digest>.json
  state/<game>/<mod-id>/*.config.json
  state/<game>/<mod-id>/*.config.originals/
  state/<game>/<mod-id>/<file-id>.load-order  # containers renamed to load last
  state/<game>/<mod-id>.json  # older per-mod record
  state/requirement_chain.json
  backups/steam-localconfig/
  downloads/
  cache/
  logs/nxm.jsonl
  ayaka/
  release/
```

The source code defines the full layout, including backup and original-file
folders. See [configuration and storage](configuration.md) before repairing
state. Storage must survive package or Distrobox removal; game files and
records need to stay in sync.

## TUI composition

`ModsService` owns the workflow state and receives `TuiHost` with explicit
adapters. Screens render service results and dispatch commands; they do not
implement site protocols or archive writes. `tui/workspace.py` provides the
shared chrome; `tui/file_table.py` and `tui/mod_detail.py` own responsive file
and artwork panes. The action picker and `:` commands share command specs.

Omarchy theme colors enter through a read-only palette adapter. The TUI can
use its built-in palette elsewhere. The app does not change desktop theme
configuration. This boundary lets tests run with named fake transports,
filesystems, browser launchers, and game shelves.

## Extension points

- Add discovery metadata and notes under `games/<id>/`; validate them with the
  catalog tests. A new manifest alone does not enable installation.
- Add a supported archive layout in a focused planner and test its accepted,
  rejected, conflict, and revert cases with fake I/O.
- Keep a new download site behind a transport or page interface and place its
  numbering in a separate staging namespace if IDs can collide.
- Put user instructions in the game adapter README and durable tradeoffs in an
  [ADR](adr/README.md).
