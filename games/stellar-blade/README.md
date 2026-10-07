# Stellar Blade adapter

Steam app ID: `3489700`. Inspect the local installation with
`omamods inspect stellar-blade`.

Standalone asset mods are placed in `SB/Content/Paks/~mods`. Some authors
ship a matching `.pak`, `.ucas`, and `.utoc` set, while others ship a single
`.pak`. The `SB/Content/Paks` parent exists in the surveyed Steam installation;
OmaMods creates `~mods` when it installs the first file.

OmaMods shares the Cronos installer and accepts these archive layouts:

| Archive contains | Installed as |
| --- | --- |
| a `~mods` folder (any depth, any case) | everything beneath it, under `~mods/` |
| one lone `.pak`, or one same-stem triplet, at the root | `~mods/<file>` |
| one folder of assets | `~mods/<folder>/<file>` |
| several variant folders | refused unless `--option` (or `option` in config) names one |

One mod author's instructions show an option folder copied intact under
`~mods` and removed intact during uninstall; the variant-folder layout follows
that. Files are never overwritten, and revert removes only unchanged files
OmaMods recorded as owned.

Mods that require a blueprint loader, UE4SS, DLL injection, or scripts are
refused as a whole (`.dll`, `.exe`, `.asi`, `.lua`, `Binaries/`, `ue4ss/`).
Custom-body and merged-asset mods may still pass these checks but conflict with
each other in game; check each mod's requirements.

Without a Nexus API key, download manually and run
`omamods nexus install stellar-blade <mod-id> <archive>`. See the root README.

Sources: [asset mod with install and uninstall steps](https://www.nexusmods.com/stellarblade/mods/3477),
[standalone `.pak` example](https://www.nexusmods.com/stellarblade/mods/1),
[loader-dependent mod example](https://www.nexusmods.com/stellarblade/mods/524).
