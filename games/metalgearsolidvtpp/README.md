# METAL GEAR SOLID V: THE PHANTOM PAIN adapter

Steam app ID: `287700`. The game runs on Konami's Fox Engine, not Unreal.
`mgsvtpp.exe` sits at the top of the game folder (`MGS_TPP/`), beside the
`master/` data folders.

## ASI plugins

[MGSVFix](https://codeberg.org/Lyall/MGSVFix) adds ultrawide support, with
HUD and graphical-effect fixes, plus resolution and framerate unlocks. Lens
dirt still renders at 16:9. Release 0.0.3 (2026-06-11) ships:

```text
EXTRACT_TO_GAME_FOLDER  (empty marker)  -> stays in staging
MGSVFix.asi                             -> MGS_TPP/MGSVFix.asi
MGSVFix.ini                             -> MGS_TPP/MGSVFix.ini
winmm.dll  (Ultimate ASI Loader)        -> MGS_TPP/winmm.dll
```

The GitHub repository (github.com/Lyall/MGSVFix) is archived at 0.0.2;
Codeberg has the current releases. OmaMods lists MGSVFix as a release mod and
downloads its newest release from the Codeberg API
(`/api/v1/repos/Lyall/MGSVFix/releases/latest`), without sending any
credentials.

Archives install whole beside `mgsvtpp.exe`: a loader DLL (`winmm.dll`,
`dinput8.dll`, `dsound.dll`, or `version.dll`), `.asi` and `.ini` files, and
`scripts/` or `plugins/` folders, which the loader also searches. A wrapping
folder is dropped. Readmes stay in staging, and any other file refuses the
archive. Existing files are never overwritten. A second plugin that ships the
same loader DLL is therefore refused until the first is uninstalled.

`.ini` files are settings you edit, so uninstalling removes them even when they
changed. Other files are removed only if their SHA-256 still matches.

Proton loads its builtin `winmm.dll` unless the Steam launch options say:

```text
WINEDLLOVERRIDES="winmm=n,b" %command%
```

Opening the game's mods and installing a plugin both warn when it is missing;
`L` shows the merged line and `c` copies it.

## Not supported

Most Nexus mods for this game are SnakeBite `.mgsv` packages, which SnakeBite
merges into the game's `.dat` archives. OmaMods refuses them with a message
naming SnakeBite.

Sources: [MGSVFix README](https://codeberg.org/Lyall/MGSVFix),
[MGSVFix releases](https://codeberg.org/Lyall/MGSVFix/releases).
