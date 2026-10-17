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

The default storage root is configurable. It must be outside the
container so a deleted Distrobox never deletes the source archives or backups.

```text
<storage-root>/
  archives/<game>/
  backups/<game>/<timestamp>/
  state/<game>/<profile>.json
```

## First implementation boundary

The CLI reads game manifests and performs read-only discovery. The first
write-capable feature is a narrowly scoped Unreal asset overlay shared by
Cronos and Stellar Blade. Each game is a `PakOverlayGame` entry in
`pak_games.py` naming its Nexus domain, `Paks` path, mods folder (`Mods` or
`~mods`), and accepted flat file sets. Nexus file metadata and an authorized
download link, or a manually downloaded file, yield a cached archive. Only
`.pak`, `.utoc`, and `.ucas` files are installed: beneath an existing mods
folder in the archive, from one variant folder copied intact, or as one flat
same-stem set. Archives with loaders or scripts are rejected, except a
complete UE4SS bundle (`ue4ss/UE4SS.dll` plus its proxy DLL), which
`ue4ss_archive.py` places in `<Project>/Binaries/Win64`; its ownership record
names that folder instead of `Paks`. An `Engine.ini` beside the bundle goes to
`Saved/Config/<platform>` in the Proton prefix (`ue_config.py`) under a second
record, `<file-id>.config.json`. It is the one install that may replace an
existing file: `original_files.py` keeps the game's copy next to that record
and revert puts it back.

Games flagged `asi_loader` (METAL GEAR SOLID V, Fox Engine) take only ASI
plugin archives. `asi_archive.py` maps a loader DLL, `.asi`/`.ini` files, and
`scripts/` or `plugins/` beside the executable, the folder `paks_subpath`
names. Revert accepts only those paths and prunes emptied plugin folders.

Mods published only as Codeberg or GitHub releases (MGSVFix) are listed in
`release_sources.py` with a small fixed mod ID. `release_api.py` reads
`/repos/<owner>/<repo>/releases/latest` through its own anonymous
`ReleaseTransport` (`TuiHost.release_transport`), so the Nexus key never
reaches those sites. `release_staging.py` keeps Nexus' staging layout under
`release/` and lists older releases' files as `OLD_VERSION`.
`tui/release_site.py` and `tui/release_actions.py` add them to the mods
screen, and `RELEASE_SITE` routes installs, reverts, and queue retries.

Launch options are written by `steam_launch_writer.py`, which edits the
`LaunchOptions` token in `localconfig.vdf` in place and backs the file up
first. `steam_process.py` closes Steam (`steam -shutdown`) before the write
and restarts it afterwards, because Steam rewrites the file on exit.
`tui/steam_setup.py` coordinates both through `TuiHost.write_launch_options`
and `TuiHost.steam`.

The staging folder is `archives/<game>/<mod-id>/`: Nexus page details in
`mod.json`, the main picture, and one subfolder per downloaded file ID.
Ownership records are per file (`state/<game>/<mod-id>/<file-id>.json`); the
older per-mod record (`state/<game>/<mod-id>.json`) is still read and reverted.

The Textual TUI (`src/omamods/tui/`) only calls `ModsService`, which receives
every host adapter through `TuiHost`: config files, Nexus transport, archive
reader, Paks locator, command runner, and GUI launcher. `textual-image` is
wrapped by `PicturePreview`. Non-Premium downloads go through the registered
`nxm://` handler (`omamods nxm handle`), which writes into the same staging
folder the TUI polls. Existing files
are never replaced, so no backup is needed for this adapter. State records
ownership hashes, and revert refuses to remove modified files. Other archive
layouts require separate adapters. A TUI can call the same core later.

## TUI workspace

`tui/workspace.py` owns shared header, mode/statusline, key hints, and terminal
size classes. `tui/styles.py` defines the fallback OmaMods Night theme and uses
Textual theme tokens so alternate palettes apply to the workspace. Main screens
share this chrome; command/search prompts keep their one-line bottom overlay.

`tui/mod_detail.py` separates the files from the optional artwork split.
`tui/file_table.py` owns responsive column widths and preserves the selected
file when resizing. Neither layout component performs host I/O.
`tui/action_picker.py` searches the existing `CommandSpec` definitions; selected
actions use the same dispatch and confirmation paths as `:` commands.

`omarchy_palette.py` validates recognized color tokens through an injected
read-only filesystem, ignoring unrelated community theme settings. Generated
`color0`–`color15` tokens provide aliases when named colors are absent.
The host supplies staged state and legacy config locations through
`TuiHost.palette_reader`; tests never inspect the desktop. The app polls once
per second, applies changed snapshots through `tui/theme_bridge.py`, and retains
the last valid snapshot during theme staging. Textual surfaces and Rich ANSI
colors use the same palette; cached text is refreshed after a change.

## Discovery implementation

The Python CLI lives in `src/omamods`. Manifest validation, Steam library
discovery, app inspection, and text reporting are separate modules. The core
receives a read-only filesystem interface; PyYAML is isolated behind a manifest
decoder. Tests inject named fake filesystems. No container or Steam process is
started by discovery.

Catalog files use `games/<id>/game.yml`. Required fields are `id` (a lowercase
slug matching the containing directory), `name`, `status` (`discovery` or
`ready`), `platforms` (`[steam]`), and `adapter` (`undecided`, `direct-overlay`,
`external-manager`, `archive-patcher`, or `game-native`). Optional fields are
`notes` (a list of nonempty strings) and `steam_app_id` (a positive integer or
null). Unknown fields, duplicate YAML keys, and unsafe tags are rejected.
These declarations do not enable mod installation.

Library discovery supports modern nested and legacy string path entries in
`libraryfolders.vdf`. Each configured app ID is matched only against its exact
`appmanifest_<id>.acf`. Missing app manifests mean no match in that library;
malformed or unreadable files and unavailable libraries produce warnings and
partial results. An installation requires the game directory and Steam's
fully-installed flag; this does not verify file integrity, compatibility, or
the executable's version. All matching library installations are reported.

`app-id-unconfigured` means matching is not yet possible. `installed` means at
least one matching installation has its directory and Steam's installed flag.
`incomplete-install` means metadata exists without both conditions.
`discovery-incomplete` means no match was found and warnings prevented a clean
inspection, including when no Steam library is accessible. `not-found` means no
match was found after scanning at least one accessible library without warnings.
