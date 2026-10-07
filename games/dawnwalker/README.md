# The Blood of Dawnwalker adapter

Steam app ID: `3751260`. The game is now released, and OmaMods can inspect a
local installation with `omamods inspect dawnwalker`.

The first proposed adapter scope is direct overlay of self-contained asset mod
files in `Dawnwalker/Content/Paks/~mods`. Mod authors document `.pak`, `.utoc`,
and `.ucas` files placed together there. The target's parent `Paks` directory
was also observed in a local Steam installation. The `~mods` directory need not
exist before any mods are installed.

This is still a discovery adapter: OmaMods does not apply mods or create that
directory. UE4SS scripts, other loaders, changes to configuration files, and
mods requiring a patcher are outside this initial overlay scope. A future
installer must identify every file in an archive, prevent collisions, check
the game build, and provide revert before touching the game.

Sources: [Steam game page](https://store.steampowered.com/app/3751260/The_Blood_of_Dawnwalker),
[mod author's installation instructions](https://www.nexusmods.com/thebloodofdawnwalker/articles/1),
[example asset mod with an explicit uninstall procedure](https://www.nexusmods.com/thebloodofdawnwalker/mods/539).
