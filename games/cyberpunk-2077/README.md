# Cyberpunk 2077 adapter

Steam app ID: `1091500`. Inspect the local installation with
`omamods inspect cyberpunk-2077`.

OmaMods installs mods and their frameworks into the game folder, the way
their pages ask: files under `archive/`, `bin/`, `engine/`, `r6/`, and
`red4ext/` keep their path, and loose `.archive`/`.xl` files go to
`archive/pc/mod`, which the game loads in ASCII name order. Pressing `i` in the
TUI installs a mod's Nexus requirements first, in dependency order; framework
files already in the game folder count as installed (see `red_frameworks.py`).
Checked against the real file layouts of RED4ext, ArchiveXL, TweakXL, Codeware,
redscript, Cyber Engine Tweaks, and Native Settings UI via Nexus' content
previews.

Under Proton, RED4ext (`winmm.dll`) and CET (`version.dll`) only load with
`WINEDLLOVERRIDES="version,winmm=n,b"` in the Steam launch options; OmaMods
reads them and warns, but does not edit Steam's config.

REDmod packages (`mods/<name>` in the game directory) are refused: the free
REDmod DLC must be installed and enabled, and the launcher deploys them.
Supporting them needs a check for the DLC and a record of load order and
deployment state before offering apply/revert. FOMOD installers are refused
too, because they need choices.

Sources: [official REDmod DLC](https://store.steampowered.com/app/2060310/REDmod/),
[REDmod user guide](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/users-modding-cyberpunk-2077/redmod/usage),
[Steam setup guide](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/users-modding-cyberpunk-2077/getting-started),
[Linux/Proton guide](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/users-modding-cyberpunk-2077/modding-on-linux).
