# METAL GEAR SOLID Δ: SNAKE EATER adapter

Steam app ID: `2417610`. The game folder holds three Unreal projects:
`MGSDelta` (the game), `MGSDelta_Foxhunt`, and `MGSDelta_Nightmare`. Mods
target `MGSDelta`.

## Pak mods

Self-contained `.pak` files and `.pak`/`.ucas`/`.utoc` sets go to
`MGSDelta/Content/Paks/~mods`, with the same archive layouts as
[Stellar Blade](../stellar-blade/README.md). The shipped paks have no `.sig`
files.

## Mods that bundle UE4SS

Some Lua mods ship UE4SS itself with the mod already enabled, for example
[BetterUncapFPS](https://www.nexusmods.com/metalgearsoliddeltasnakeeater/mods/47)'s
"UE4SS_All in One Package":

```text
dwmapi.dll                       -> MGSDelta/Binaries/Win64/dwmapi.dll
ue4ss/UE4SS.dll, Mods/, ...      -> MGSDelta/Binaries/Win64/ue4ss/...
Engine.ini                       -> <prefix>/.../MGSDelta/Saved/Config/Windows/Engine.ini
changelogs                       -> stay in staging
```

OmaMods installs such an archive as a whole beside
`MGSDelta-Win64-Shipping.exe`. It needs both `ue4ss/UE4SS.dll` and a proxy DLL
(`dwmapi.dll`, or `xinput1_3.dll` for UE4SS 2.x). Standalone UE4SS mods, which
would have to be merged into an existing `ue4ss/Mods/mods.txt`, and Blueprint
`LogicMods` are refused for now. Two bundles both ship `ue4ss/UE4SS.dll`, so
the second is refused with the file's name; uninstall the first.

Proton loads its own `dwmapi.dll` unless told otherwise, so the Steam launch
options need:

```text
WINEDLLOVERRIDES="dwmapi=n,b" %command%
```

Opening the game's mods and installing a bundle both warn when it is missing;
`L` shows the merged line and `c` copies it.

Lua mods rewrite their own settings (BetterUncapFPS saves
`UncapFPS_config.txt`), so `.txt`, `.ini`, `.json`, and `.cfg` files under
`ue4ss/` are removed on uninstall even when they changed. Every other file is
removed only if its SHA-256 still matches. Files UE4SS creates at run time,
such as `UE4SS.log`, are not OmaMods' and keep `ue4ss/` in place.

An `Engine.ini` (or `Game.ini`, `Input.ini`, `Scalability.ini`,
`GameUserSettings.ini`) beside the bundle goes to
`%LOCALAPPDATA%/MGSDelta/Saved/Config/Windows/` inside the Proton prefix. The
game already keeps its own `Engine.ini` there, so OmaMods moves that one into
storage (`state/<game>/<mod>/<file>.config.originals/`) and puts it back on
uninstall, even if the game rewrote the mod's copy in the meantime. The game
has to have been launched once, so that the folder exists.

Sources: [UE4SS installation guide](https://docs.ue4ss.com/dev/installation-guide.html),
[MGS Delta Vortex extension notes](https://www.nexusmods.com/site/mods/1411).
