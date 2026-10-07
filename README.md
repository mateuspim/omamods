# OmaMods

OmaMods is an Arch-first tool for reproducible game-mod profiles.

It coordinates Steam, Proton, Distrobox and the mod tools that games already
use. It does not try to replace every game-specific mod manager.

## First target

The Blood of Dawnwalker is the first game adapter. Its initial job is to prove
the workflow: discover a Steam game, preserve mod archives outside a Distrobox,
record a versioned profile, apply it safely, and restore the original state.
The first write-capable adapter covers self-contained Unreal asset mods for
Cronos and Stellar Blade. Discovery manifests also cover SILENT HILL 2,
Divinity: Original Sin 2, and Cyberpunk 2077. Their adapter types describe
proposed workflows, not working installers.

## Project principles

- Keep manifests, install rules and profiles in Git.
- Keep downloaded archives and backups in persistent host storage.
- Treat each game as an adapter: direct overlay, external manager, archive
  patcher, or a game-native manager.
- Verify game versions and archive contents before applying a profile.
- Make every managed change reversible.

## Run the discovery CLI

Requires Python 3.12 or newer. From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
omamods game list
omamods inspect dawnwalker
omamods inspect silent-hill-2
```

If Python and PyYAML are already installed, you can also run without installing
the package:

```sh
PYTHONPATH=src python -m omamods inspect dawnwalker
```

`game list` lists games declared in this repository, with their local installation
status. `inspect` reports discovered libraries and, for games with a configured
Steam app ID, game directories, Steam build IDs, installation flags, and existing
Proton prefixes. A Steam build ID is metadata, not a verified executable version.
Neither command writes to Steam, game directories, or Proton prefixes.

## Terminal UI

```sh
omamods        # same as `omamods tui`
```

To run `omamods` from any directory while you work on the code, install it as
an editable [uv](https://docs.astral.sh/uv/) tool. Code changes apply at once;
reinstall only after changing dependencies in `pyproject.toml`:

```sh
uv tool install --editable .            # puts omamods in ~/.local/bin
uv tool install --editable --reinstall . # after dependency changes
uv tool uninstall omamods
```

1. Press `k` once and paste your personal Nexus API key
   (nexusmods.com/users/myaccount?tab=api). It is saved to the private config.
2. Press `n` once so the site's **Mod Manager Download** button hands files
   to OmaMods (registers `omamods-nxm.desktop` as the `nxm://` handler with
   `xdg-mime`; it reports the handler it replaced).
3. Pick a game, press `a`, paste a mod page URL, and choose files. Every
   current file is preselected (old and archived versions are not). They
   download into the staging folder,
   `<storage-root>/archives/<game>/<mod-id>/<file-id>/`, next to the mod's
   details (`mod.json`) and main picture.
4. Press `i` to install the mod: all staged MAIN, UPDATE, MISCELLANEOUS, and
   hand-downloaded files at once. OPTIONAL files are left out because they are
   often alternatives. You pick a variant for any archive that has several,
   files that would write the same game file are refused with both names, and
   the exact target paths are shown before anything is written.
5. Press Enter on a file to install or uninstall just that file, e.g. to swap
   a main file for an optional one. `u` uninstalls the whole mod, `x` deletes
   the selected download from staging (not if installed), `o` opens
   the picture in `imv`, and `w` opens the mod page.

### Vim keys and commands

`j`/`k` move, `gg`/`G` jump to the top/bottom, `Ctrl+d`/`Ctrl+u` page, and
`h`/`l` switch panes. `/text` jumps to a mod whose name contains `text`;
`n`/`N` find the next/previous match. `:` opens a command line (Tab or the
right arrow accepts the suggestion); commands accept unique prefixes like vim,
so `:inst` is `:install`. `:help` lists the commands for the current screen.

| Command | Does |
| --- | --- |
| `:q`, `:qa` | close this screen, quit OmaMods |
| `:game <name>` | open a game by ID prefix, name, or initials (`:game sb`) |
| `:add <url>` | add a mod; opens the URL's game |
| `:install [file]`, `:uninstall [file]` | the whole mod, or one file |
| `:download [file\|all]` | the selected file, one file, or every current file |
| `:rm <file>` | delete a download from staging |
| `:queue`, `:retry`, `:clear` | the download queue |
| `:key <api-key>`, `:nxm` | setup |

A `file` is its number in the **ID** column or a unique part of its name; when
a name matches an old and a current version, the current one wins. The API-key
prompt moved from `k` to `K` because `k` now moves up.

Premium keys download directly. Without Premium, Nexus only allows downloads
started on its site: the TUI opens the file's page, and your click on **Mod
Manager Download** runs `omamods nxm handle`, which downloads into staging and
sends a desktop notification. The TUI picks the file up within a few seconds.
With a Chromium-family default browser (Brave, Chromium, Vivaldi, ...) on
Hyprland, the page opens in its own app window showing the first file's
download popup. As each file arrives, the TUI moves the window on to the next
file's popup, and closes it once every file you chose has arrived. To float
and centre that window, add an Omarchy window rule to
`~/.config/hypr/hyprland.lua`:

```lua
o.window("^brave-www\\.nexusmods\\.com__.*", { float = true, center = true, size = { 1280, 860 } })
```

Use your browser's class prefix (`chromium-`, `vivaldi-`, ...) instead of
`brave-` if needed. Other browsers get a
normal tab that stays open.
Handler results are logged as JSON lines in `<storage-root>/logs/nxm.jsonl`.
The notification names the file the click actually delivered (name, version,
category) and warns when it is an old version. If a click delivers a file you
did not ask for, the TUI says so and names the file it is still waiting for.

Press `D` on any screen to open the download queue. It lists every download,
including ones started by browser clicks, with state, progress, speed, time
left, and seconds since data last arrived. A download with no new data for 20
seconds shows as **stalled**. Dropped connections, timeouts, and server errors
(429/5xx) are retried up to five times with growing waits (2-16 s), resuming
where the download stopped; the Error column shows `retrying 2/5 after: ...`.
Expired or refused links (403/404/410) fail at once. Otherwise, `r` retries the selected failed, stalled, or
waiting download and `c` clears finished entries. Each download writes a small
status file to `<storage-root>/downloads/`, which is how the TUI sees
downloads running in the separate browser-handler process.

Pictures render inline in Kitty, Ghostty, and foot; other terminals such as
Alacritty show a coarse block preview, with `o` for full quality.

## Cronos and Stellar Blade Nexus mods

Both games share one installer for self-contained `.pak`/`.utoc`/`.ucas` mods.
Stellar Blade mods go to `SB/Content/Paks/~mods`; see the
[Stellar Blade adapter](games/stellar-blade/README.md) for the archive layouts
it accepts.

### Manual downloads (no API key)

Download the archive from the mod page's **Files** tab with **Manual
Download**, then pass the mod ID from the page URL
(`nexusmods.com/stellarblade/mods/<mod-id>`):

```sh
omamods nexus install stellar-blade 1 ~/Downloads/SomeMod-1-1-0-1700000000.zip
omamods nexus install stellar-blade 3477 ~/Downloads/Outfit.zip --option "Black"
omamods nexus revert stellar-blade 1
```

Each staged file installs and reverts on its own, so a mod's main file and an
optional add-on can both be installed; pass `--file-id` to `revert` to remove
just one file.

A private config is optional here. The archive is copied into persistent
storage first, so the copy in `~/Downloads` can be deleted. If an archive holds
several variant folders, the error lists them; pick one with `--option`.
Archives that contain loaders or scripts (`.dll`, `.exe`, `.asi`, `.lua`,
`Binaries/`, `ue4ss/`) are refused as a whole.

### API downloads

The Cronos adapter installs archives containing a `Mods` directory into
`Cronos/Content/Paks`, matching [mod 38's installation instructions](https://www.nexusmods.com/cronosthenewdawn/mods/38).
It also accepts mod 38's current flat `.pak`/`.utoc`/`.ucas` triplet and
places those files under `Paks/Mods`.
Install `bsdtar` (`libarchive` on Arch) to read ZIP, 7z, or RAR archives. Close
the game before installing or reverting.

```sh
omamods config init
```

This creates `~/.config/omamods/config.toml` with mode `0600` (or under
`XDG_CONFIG_HOME`) and preselects mod 38. Edit that file to set your personal
Nexus API key under `[nexus]`; alternatively set `NEXUS_API_KEY` in your shell.
The config and downloaded archives are outside Git. Archives default to
`~/.local/share/omamods` (or `XDG_DATA_HOME/omamods`). Set
`[storage] root = "/absolute/path"` to use another persistent host location.
If several Steam installations are found, set
`[games.cronos] install_dir = "/absolute/path/to/Cronos. The New Dawn"`.
Add more `[[mods]]` entries with `game = "cronos"` or `game = "stellar-blade"`
and a Nexus mod page URL; set `file_id` when a page has multiple main files and
`option` to choose a variant folder. Use `[games.stellar-blade] install_dir` the
same way as for Cronos.

```sh
omamods nexus sync cronos --mod-id 38 --download-only
omamods nexus sync cronos --mod-id 38
omamods nexus revert cronos 38
```

Premium accounts can use the personal API key alone. For non-premium accounts,
click **Mod Manager Download** on the chosen file and pass its short-lived NXM
link with `--nxm-link 'nxm://...'`. Shell history can retain this link, so use
care when entering it. The downloader does not bypass Nexus account or download
restrictions. It never overwrites an existing game file; revert removes only
unchanged files recorded as owned. For an alternate config, put `--config
/absolute/path/config.toml` before the command.

Native Steam, `XDG_DATA_HOME`, and Flatpak Steam locations are checked, including
additional libraries from `steamapps/libraryfolders.vdf`. Symlink aliases are
deduplicated. For custom locations, put global options before the command:

```sh
omamods --games-dir /path/to/omamods/games --steam-root /path/to/Steam inspect dawnwalker
```

`--games-dir` defaults to `./games`; pass it when running outside this checkout.
Repeat `--steam-root` for multiple clients; explicit roots replace automatic
root discovery. Missing game installations and unconfigured app IDs are normal
results. Exit codes are `0` for a completed inspection, `1` for partial results
with discovery warnings, and `2` for invalid input or unreadable catalog files.

## Development

Run all tests with this single command from the repository root, using the
environment above:

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

Tests use named fake I/O adapters and temporary directories; they never inspect
or modify your Steam setup.
Format Python with `python -m black src tests`.

## Future commands

```text
omamods profile apply dawnwalker/default
omamods profile revert dawnwalker/default
omamods manager open <game>
```

General profiles, backups, and manager launching are not implemented. The
Unreal asset installer for Cronos and Stellar Blade and its ownership-based
revert are the first narrow write-capable commands.

See [the architecture](docs/architecture.md) and the
[Dawnwalker adapter](games/dawnwalker/README.md).
