# Game workflows

Engine layouts and game adapters determine which archives OmaMods can install.
A game listed in the catalog is not automatically mod-ready.

## Auto-detected Unreal games

Each scan also checks every installed game for an Unreal Engine layout
(`<Project>/Content/Paks/*.pak`, ignoring `Engine/`). When the game's title
matches a game on Nexus, it moves to **Mod-ready** and uses the same pak
installer as Cronos and Stellar Blade: mods go to `Content/Paks/~mods`, and
IoStore games (`.utoc` present) accept both lone `.pak` files and
`.pak/.ucas/.utoc` sets. Games that ship `.sig` files carry a warning, since
they may refuse unsigned paks. Archives that bundle UE4SS itself (a
`dwmapi.dll` and a `ue4ss/` folder) install beside the game's executable, and
an `Engine.ini` beside them replaces the game's own in the Proton prefix until
uninstalled, as described for [METAL GEAR SOLID Δ](../games/metalgearsoliddeltasnakeeater/README.md);
standalone UE4SS mods, Blueprint `LogicMods`, and other DLL loaders are still
refused.

Title matching uses Nexus' game list, which needs an API key once and is cached
for a week in `<storage>/cache/nexus_games.json`. Unreal games with no match
stay in their group with a note. The scan's results are saved to
`<storage>/detected_games.json` so the `nxm` handler, which runs as its own
process, can stage downloads for them.

## Auto-detected RE Engine games

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

Opening Cyberpunk's mods warns when RED4ext or CET is installed without the
override or with an old runtime. `L` there shows what Steam has now next to
the full line to paste (your other options kept, the override merged in) and
the protontricks command. `w` saves the line into Steam for you (see
[Saving launch options to Steam](#saving-launch-options-to-steam)). `c` copies
the line and `p` the command, with `wl-copy` and the terminal's clipboard.
OmaMods never changes the Proton prefix. The requirements dialog shows the same and
copies with the same keys. A `modlist.txt` in
`archive/pc/mod` overrides the archives' name order; OmaMods does not edit it.
See the [Cyberpunk 2077 adapter](../games/cyberpunk-2077/README.md).

### Saving launch options to Steam

`w` in the `L` dialog writes the suggested line into the game's
`LaunchOptions` in every Steam user's `userdata/<id>/config/localconfig.vdf`
that lists the game. Only that one value changes; the rest of the file stays
byte for byte. Each file is first copied to
`<storage-root>/backups/steam-localconfig/<timestamp>/<user id>/`.

Steam keeps that file in memory and writes it back when it exits, so an edit
made while Steam runs would be lost. If Steam is running, OmaMods asks first,
then closes it (`steam -shutdown`, which also closes a running game), writes
the file, and starts Steam again in the tray (`steam -silent`). If Steam has
never shown the game's settings, its block is missing from the file; open the
game's Properties in Steam once and try again.

## METAL GEAR SOLID Δ: SNAKE EATER

Pak mods go to `MGSDelta/Content/Paks/~mods`. Mods that ship UE4SS with them,
such as BetterUncapFPS' "UE4SS_All in One Package", install whole into
`MGSDelta/Binaries/Win64` (their `Engine.ini` goes to the game's config folder
in the Proton prefix and the original comes back on uninstall), and need `WINEDLLOVERRIDES="dwmapi=n,b"` in the
Steam launch options; the mods screen warns when it is missing and `L` shows
the line to paste. See the
[METAL GEAR SOLID Δ adapter](../games/metalgearsoliddeltasnakeeater/README.md).

## METAL GEAR SOLID V: THE PHANTOM PAIN

The game has no ultrawide support of its own. Its mods list always shows
[MGSVFix](https://codeberg.org/Lyall/MGSVFix), Lyall's fix for ultrawide
resolutions (HUD and effects included), resolution choice, and the framerate
cap. It is published only as Codeberg releases, not on Nexus. `d` asks
Codeberg for the newest release and downloads its zip. `i` then puts
`MGSVFix.asi`, `MGSVFix.ini`, and the ASI loader `winmm.dll` beside
`mgsvtpp.exe`. Proton only loads that `winmm.dll` with this in the Steam
launch options:

```text
WINEDLLOVERRIDES="winmm=n,b" %command%
```

The mods screen warns when it is missing. `L` shows the line, and `w` there
saves it into Steam. Opening the screen checks Codeberg again and says when a newer release than
the installed one is out: `u`, `d`, then `i` updates. Uninstalling removes
`MGSVFix.ini` even after you edited it, so copy your settings first.

Other archives with `.asi` plugins (a loader DLL, `.asi` and `.ini` files, or
a `scripts/` or `plugins/` folder) install the same way, from Nexus or by
hand. A second plugin that ships its own `winmm.dll` is refused while another
mod owns that file. SnakeBite `.mgsv` packages, which most MGSV Nexus mods
are, are refused. See the
[METAL GEAR SOLID V adapter](../games/metalgearsolidvtpp/README.md).

Release mods keep their own staging and install records under
`<storage-root>/release/`. The built-in list of repositories lives in
`src/omamods/release_sources.py`; Codeberg and GitHub are supported.

## Cronos and Stellar Blade Nexus mods

Both games share one installer for self-contained `.pak`/`.utoc`/`.ucas` mods.
Stellar Blade mods go to `SB/Content/Paks/~mods`; see the
[Stellar Blade adapter](../games/stellar-blade/README.md) for the archive layouts
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
