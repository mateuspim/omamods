# OmaMods

OmaMods is an Arch-first tool for reproducible game-mod profiles.

It coordinates Steam, Proton, Distrobox and the mod tools that games already
use. It does not try to replace every game-specific mod manager.

## First target

The Blood of Dawnwalker is the first game adapter. Its initial job is to prove
the workflow: discover a Steam game, preserve mod archives outside a Distrobox,
record a versioned profile, apply it safely, and restore the original state.
The first write-capable adapter covers self-contained Unreal asset mods for
Cronos and Stellar Blade; Cyberpunk 2077's `.archive` mods use the same
installer. Discovery manifests also cover SILENT HILL 2 and Divinity: Original
Sin 2. Their adapter types describe proposed workflows, not working installers.

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

The home screen scans for games each time it opens (press `r` to rescan) and
lists them in three groups:

- **Mod-ready**: catalog games OmaMods can install mods for (Cronos, Stellar
  Blade, Cyberpunk 2077, METAL GEAR SOLID Δ), plus detected Unreal and RE Engine games. Enter
  opens their mods.
- **In the catalog**: games with a manifest but no installer yet.
- **Your other games**: every other game Steam has installed, in any library
  `libraryfolders.vdf` lists, plus Epic, GOG, Amazon, and sideloaded games
  from Heroic Games Launcher (native or Flatpak). Proton, the Steam Linux
  Runtime, and Steamworks redistributables are hidden.

### Auto-detected Unreal games

Each scan also checks every installed game for an Unreal Engine layout
(`<Project>/Content/Paks/*.pak`, ignoring `Engine/`). When the game's title
matches a game on Nexus, it moves to **Mod-ready** and uses the same pak
installer as Cronos and Stellar Blade: mods go to `Content/Paks/~mods`, and
IoStore games (`.utoc` present) accept both lone `.pak` files and
`.pak/.ucas/.utoc` sets. Games that ship `.sig` files carry a warning, since
they may refuse unsigned paks. Archives that bundle UE4SS itself (a
`dwmapi.dll` and a `ue4ss/` folder) install beside the game's executable, and
an `Engine.ini` beside them replaces the game's own in the Proton prefix until
uninstalled, as described for [METAL GEAR SOLID Δ](games/metalgearsoliddeltasnakeeater/README.md);
standalone UE4SS mods, Blueprint `LogicMods`, and other DLL loaders are still
refused.

Title matching uses Nexus' game list, which needs an API key once and is cached
for a week in `<storage>/cache/nexus_games.json`. Unreal games with no match
stay in their group with a note. The scan's results are saved to
`<storage>/detected_games.json` so the `nxm` handler, which runs as its own
process, can stage downloads for them.

### Auto-detected RE Engine games

Capcom's RE Engine games (Resident Evil 2, 3, 4, 7, and Village, Devil May
Cry 5, Monster Hunter Rise and Wilds, Dragon's Dogma 2, Street Fighter 6, ...)
are recognised by the `re_chunk_000.pak` in their folder and become
**Mod-ready** the same way. The RE Engine remakes share their Steam titles with
the originals, so Resident Evil 2, 3, 4 (2023), and 7 are matched to their
Nexus pages by Steam app ID instead of by title.

These games load mods as numbered patches of the base pak, starting at
`patch_001` and stopping at the first missing or 0-byte patch. Each `.pak`
in a mod archive therefore takes the lowest missing or empty
`re_chunk_000.pak.patch_NNN.pak`. RE7 ships 0-byte `patch_002` to `patch_008`
and no `patch_001`, so its mods become `patch_001`, `patch_002`, and so on;
uninstalling puts Capcom's 0-byte files back. Games that ship a `sub_000` pak use
`re_chunk_000.pak.sub_000.pak.patch_NNN.pak` instead, such as Monster Hunter
Wilds. Fluffy Mod Manager archives work too: as
Fluffy does, their loose `natives/` files are packed into one new patch pak
(uncompressed KPKA 4.0, so it can be larger than the download). `modinfo.ini`
and pictures are ignored, and each folder holding a `natives/` folder or
`.pak` files is offered as a variant; each variant installed becomes its own
patch. Packing needs a version 4 base pak;
older builds such as RE7's non-RT branch are refused. Mods installed later
override earlier ones that change the same files. Uninstalling a mod that
sits below another leaves an empty patch in its place, because the chain must
not have gaps. REFramework scripts and
DLL loaders are refused.

A game update can add an official patch with a number a mod already uses and
overwrite it. OmaMods then refuses to uninstall the changed file; reinstall
your mods after a game update.

The detail panel shows the game's folder, library, size, Steam app ID, build,
and Proton prefix. `o` opens the folder in your file manager, `/` filters by
name, and `w` lists records that could not be read. Catalog games match Steam
installs by app ID, never by title. Colors follow Omarchy's current theme, with
OmaMods Night as a fallback; `Ctrl+P` → *Change theme* selects a session palette.

1. Press `K` once and paste your personal Nexus API key
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
   often alternatives. For any archive with several variant folders, a list
   shows them: Space toggles, Enter installs every ticked variant. Variants
   holding the same file names (colours of one outfit, say) are alternatives:
   they start unticked, and ticking one unticks the others. Only the innermost
   folders are variants; paks in a folder above a variant (an outfit's shared
   "Addons", say) install with it. Unreal variants keep their folder path
   under `~mods` (`~mods/hero/armor/black/`). Archives packed inside the
   archive are not installed, and a warning names them.
   Each variant is recorded separately, and uninstalling the file removes all
   of them. Files that would write the same game file are refused with both names, and
   the exact target paths are shown before anything is written.
5. Press Enter on a file to install or uninstall just that file, e.g. to swap
   a main file for an optional one. `u` uninstalls the whole mod, `x` deletes
   the selected download from staging (not if installed), `o` opens
   the picture in `imv`, and `w` opens the mod page.

### Vim keys and commands

The workspace follows your **active Omarchy theme**, including its status and
search colors. Changes apply live, within a second, without restarting OmaMods.
It reads Omarchy's staged `colors.toml` under `~/.local/state/omarchy/current/theme`
(or the legacy config location), without changing desktop configuration. If
Omarchy is absent, the **OmaMods Night** palette is used. A partially written
palette keeps the last valid colors until the update finishes.
Both named colors and Omarchy's generated `color0`–`color15` palettes are
supported. Community theme settings such as terminal opacity and border
gradients are ignored when reading colors.

`Ctrl+p` → **Change theme** selects another palette for the session; the next
Omarchy theme change resumes desktop sync. The bottom statusline shows the
interaction mode, active pane, and cursor position. The key hints follow focus:
files show Enter's exact action, and queues show retry and clear keys.
**Space** opens a searchable action picker: type a name or
description, use `↑`/`↓` (or `Ctrl+j`/`Ctrl+k`) to select, and Enter to run it.
Actions needing an argument open a prefilled `:` line.

Mod files and artwork have independent panes. **p** (or `:preview`) toggles the
artwork; narrow or short terminals hide it automatically to keep the files
visible. The file table adapts too: compact splits show state, filename, and
category; wider splits also show version, size, and file ID. Filenames remain
beside their installed, staged, or available state. The inspector keeps artwork
in proportion and describes the highlighted file's next action. Very wide
terminals center the workspace at a comfortable reading width.

`j`/`k` move, `gg`/`G` jump to the top/bottom, `Ctrl+d`/`Ctrl+u` page, and
`h`/`l` switch panes. `/` filters the games or mods list as you type, like a
LazyVim picker: only names containing every typed word stay, with the words
highlighted, and the panel title shows the filter and its count. Enter keeps the
filter, Esc in the prompt puts back the previous one, and Esc on the list clears
it while staying on the highlighted entry (a second Esc leaves the mods screen).
On the mods screen `n`/`N` cycle through the matches. The `:` and `/` lines sit
on the bottom row like vim's, and `/` shows the live match count there. In the
mods list, `●` marks mods with an installed file and `○` mods that are only
staged.

`:` opens a command line (Tab or the right arrow accepts the suggestion);
commands accept unique prefixes like vim, so `:inst` is `:install`. `:help`
lists the commands for the current screen.

| Command | Does |
| --- | --- |
| `:q`, `:qa` | close this screen, quit OmaMods |
| `:game <name>` | open a game by ID prefix, name, or initials (`:game sb`) |
| `:add <url>` | add a Nexus or AyakaMods mod; opens the URL's game |
| `:install [file]`, `:uninstall [file]` | the whole mod, or one file |
| `:download [file\|all]` | the selected file, one file, or every current file |
| `:rm <file>` | delete a download from staging |
| `:queue`, `:retry`, `:clear` | the download queue |
| `:dl [min\|game\|full]` | size the mods screen's downloads panel |
| `:preview` | toggle the artwork split (`p`) |
| `:stop` | stop waiting for an AyakaMods download |
| `:nsfw [blur\|hide\|show\|mark\|unmark]` | blur, hide, or show NSFW mods, or mark the selected one |
| `:ayaka-login [xf_user]` | save your AyakaMods login (guided without a value) |
| `:key <api-key>`, `:nxm` | setup |

### NSFW mods

Mods Nexus flags as adult content show a red `18+`. `H` steps through three
modes, which apply to every game and are remembered:

1. **Blur** (default): NSFW mods stay listed, but their picture is heavily
   blurred. `o` still opens the real picture in `imv`.
2. **Hide**: NSFW mods leave the list; the panel's bottom edge counts them.
3. **Show**: NSFW mods and their pictures appear as they are.

`m` marks or unmarks the selected mod as NSFW by hand, for AyakaMods and
hand-staged mods or when Nexus' flag is wrong; a hand mark wins over the flag.
Both are kept in `<storage>/adult_marks.json`. Mods staged before OmaMods read
the flag have none until you add them again (`a` and their URL) or mark them.

### Downloads panel

The mods screen keeps the download queue in a panel along its bottom edge.
`D` grows it in three steps and then shrinks it back:

1. **Minimized** (default): one summary line for every game's downloads, for
   example `↓ Downloads: 1 downloading (ArchiveXL 45% · 1.2 MB/s) · 1 waiting
   for browser · 3 done`. The name in brackets is this game's running download.
2. **This game**: a short table of this game's queue under the mods and
   details.
3. **All games**: the whole queue fills the screen, hiding the mods.

In either table, `r` retries the highlighted download and `c` clears done and
failed ones; `l`/`h` move focus into and out of the table. `:dl full` (or
`min`, `game`) jumps straight to a size. On other screens `D` still opens the
separate queue screen, which `:queue` opens from anywhere.

A `file` is its number in the **ID** column or a unique part of its name; when
a name matches an old and a current version, the current one wins. The API-key
prompt moved from `k` to `K` because `k` now moves up.

Premium keys download directly. Without Premium, Nexus only allows downloads
started on its site: the TUI opens the file's page, and your click on **Mod
Manager Download** runs `omamods nxm handle`, which downloads into staging and
sends a desktop notification. The TUI picks the file up within a few seconds.
With a Chromium-family default browser (Brave, Chromium, Vivaldi, ...) on
Hyprland, the page opens in its own app window showing the first file's
download popup. Once your click starts a download, the TUI moves the window
out of sight to Hyprland's hidden `special:omamods` workspace (Hyprland has no
minimise; `hyprctl dispatch togglespecialworkspace omamods` peeks at it). As
each file arrives, the TUI opens the next file's popup in a fresh window, and
closes it once every file you chose has arrived. If a download fails, the
popup comes back so you can click again. To float
and centre that window (and AyakaMods' page window), add Omarchy window rules to
`~/.config/hypr/hyprland.lua`:

```lua
o.window("^brave-www\\.nexusmods\\.com__.*", { float = true, center = true, size = { 1280, 860 } })
o.window("^brave-ayakamods\\.com__.*", { float = true, center = true, size = { 1280, 860 } })
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

### AyakaMods

Press `a` (or `:add`) and paste an AyakaMods page URL, such as
`https://ayakamods.com/mods/sample-outfit.7311/`. No API key is
needed: OmaMods reads the name, author, version, picture, and game from the
page, and refuses a mod made for another game. `:add` from any screen opens
the game the page names.

AyakaMods only serves files to a logged-in user and has no mod-manager link
like Nexus' `nxm://`. To download like Nexus, OmaMods needs your login once.
The first time you add or download an AyakaMods mod without one (or once it
expires), OmaMods opens the AyakaMods login page in your browser and a prompt
in the terminal:

1. Log in on ayakamods.com with **Stay logged in** ticked.
2. Open DevTools (`F12`) > **Application** > **Cookies** >
   `https://ayakamods.com` and copy the value of `xf_user` (it looks like
   `347376%2CAbC...`).
3. Back in OmaMods the prompt has already filled it in from the clipboard
   (`wl-paste`; anything not shaped like that cookie is ignored). Press Enter
   and the download starts. Esc downloads through the browser instead.

`:ayaka-login` opens the same prompt any time, and `:ayaka-login <value>` saves
a value directly. The cookie is kept in the private config as
`[ayaka] login_cookie`, like the Nexus key, and is sent only to ayakamods.com,
never to a host a download redirects to.

Then adding a mod (or `d` on one) downloads it straight into staging, with
progress, retries, and resume in the downloads panel. A mod with several files
opens the file picker first. Treat the cookie like a password: it logs in as
you until you log out of AyakaMods in the browser, which also ends it.

Without a saved login, or when it has expired, or when a mod is hosted on
another site (Mega, Drive, ...), OmaMods opens the mod page instead (in its own
app window with a Chromium-family browser, as for Nexus) and watches your
downloads folder (`xdg-user-dir DOWNLOAD`, else `~/Downloads`). Download the
file there as usual. Once the browser has finished writing it, the archive is
moved into staging, the window closes, and `i` installs it like any other
mod. Files already in the folder are ignored, and partial `.crdownload` and
`.part` files are waited out. If your browser asks where to save, pick that
folder.

OmaMods waits for one browser download at a time; adding another mod
replaces the wait, and `:stop` ends it. Anything else that finishes
downloading into the folder while it waits is taken as that mod's file, so
`x` deletes it from staging if it was not. The Nexus requirement check does
not apply to AyakaMods mods.

AyakaMods mods keep their own staging and install records under
`<storage-root>/ayaka/`, because the two sites number their mods
independently.

## Cyberpunk 2077 Nexus mods

Cyberpunk 2077 (Steam) mods and their frameworks (RED4ext, ArchiveXL,
TweakXL, Codeware, redscript, Cyber Engine Tweaks) install into the game
folder, as their pages ask. Files under `archive/`, `bin/`, `engine/`, `r6/`,
or `red4ext/` keep their path, a wrapping folder such as `Cyberpunk 2077/` is
dropped, and loose `.archive` and `.xl` files go to `archive/pc/mod`. Archives
with several variant folders open the variant picker. REDmod packages
(`mods/` at the top) and FOMOD installers are refused. As for every game,
existing files are never overwritten, and uninstalling removes only files whose
SHA-256 still matches, then any folders that emptied (never the game's own
`archive/`, `bin/`, `engine/`, or `r6/`).

### Requirements

With an API key, `i` first asks Nexus (its v2 GraphQL API, which also lists
requirements a mod's description leaves out) for the mod's whole requirement
tree. Requirements that OmaMods installed, or whose files are already in the
game folder, are skipped. If any are missing, a dialog lists them in install
order with the file it picked (the newest MAIN file), plus DLC and off-site
requirements you must check yourself. Confirming downloads them one at a time
(without Premium, one Nexus window per click) and installs each as soon as it
arrives, then installs the mod. A failed download or install stops the chain.
Enter on a staged file and `:install` check requirements the same way. The
running chain is saved to `<storage>/state/requirement_chain.json`, so closing
the TUI midway is safe: on the next start it installs whatever arrived and
reopens the next download. The dialog marks each row "downloaded" or "to
download".

RED4ext and Cyber Engine Tweaks load through `winmm.dll` and `version.dll`,
which Proton ignores unless told otherwise. When the plan includes them and
the game's Steam launch options lack the override, the dialog says what to
add, for example:

```text
WINEDLLOVERRIDES="version,winmm=n,b" %command%
```

RED4ext 1.30 and CET 1.37 also need the Visual C++ runtime 14.40 or newer in
the game's Proton prefix; with the game's own 2020 redistributable (14.28) CET
fails with "Unable to load cyber_engine_tweaks.asi, Error: 998". OmaMods reads
`msvcp140.dll`'s version from `steamapps/compatdata/<app id>/pfx` and, when it is
older, suggests `protontricks 1091500 -q vcrun2022` (run it with the game
closed).

OmaMods reads the launch options and the prefix but changes neither. Opening
Cyberpunk's mods warns when RED4ext or CET is installed without the override or
with an old runtime; `L` there shows what Steam has now next to the full line
to paste (your other options kept, the override merged in) and the
protontricks command. `c` copies the line and `p` the command, with `wl-copy`
and the terminal's clipboard. The requirements dialog shows the same and
copies with the same keys. A `modlist.txt` in
`archive/pc/mod` overrides the archives' name order; OmaMods does not edit it.
See the [Cyberpunk 2077 adapter](games/cyberpunk-2077/README.md).

## METAL GEAR SOLID Δ: SNAKE EATER

Pak mods go to `MGSDelta/Content/Paks/~mods`. Mods that ship UE4SS with them,
such as BetterUncapFPS' "UE4SS_All in One Package", install whole into
`MGSDelta/Binaries/Win64` (their `Engine.ini` goes to the game's config folder
in the Proton prefix and the original comes back on uninstall), and need `WINEDLLOVERRIDES="dwmapi=n,b"` in the
Steam launch options; the mods screen warns when it is missing and `L` shows
the line to paste. See the
[METAL GEAR SOLID Δ adapter](games/metalgearsoliddeltasnakeeater/README.md).

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
Install `bsdtar` (`libarchive` on Arch) to read ZIP, 7z, or RAR archives,
and `7z` (`7zip` on Arch) for RAR5 archives that libarchive refuses with
"Declared dictionary size is not supported". Close
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
