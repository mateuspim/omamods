# Cyberpunk 2077 adapter

Steam app ID: `1091500`. Inspect the local installation with
`omamods inspect cyberpunk-2077`.

This adapter initially targets REDmod packages and the official launcher. The
free REDmod DLC is separate from the base game and must be installed and
enabled. REDmod packages live under `mods/<name>` in the game directory, and
the launcher deploys and activates them. Legacy archive mods use a different
path and can coexist, but should not be treated as REDmod packages.

OmaMods currently only inspects the base game. Later work should check the DLC,
distinguish REDmod from legacy archive mods, and record load order and
deployment state before offering apply/revert. Linux/Proton has additional
prerequisites for some mod frameworks; these need explicit verification per
mod rather than an assumed generic launcher recipe.

Sources: [official REDmod DLC](https://store.steampowered.com/app/2060310/REDmod/),
[REDmod user guide](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/users-modding-cyberpunk-2077/redmod/usage),
[Steam setup guide](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/users-modding-cyberpunk-2077/getting-started),
[Linux/Proton guide](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/users-modding-cyberpunk-2077/modding-on-linux).
