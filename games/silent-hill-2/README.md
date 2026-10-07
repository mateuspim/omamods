# SILENT HILL 2 adapter

Steam app ID: `2124490`. Inspect the local installation with
`omamods inspect silent-hill-2`.

The initial proposed scope is direct overlay of a mod author's standalone
`.pak` file into `SHProto/Content/Paks/~mods`. A mod author explicitly documents
this destination. The `SHProto/Content/Paks` parent directory exists in the
local Steam install; the `~mods` directory is not present yet.

Other mods place files directly in `Paks`, change config in the Proton prefix,
or require a loader or manager. Those need their own rules. There is no
write-capable adapter yet; archive contents, game build, conflicts, and revert
must be checked before installation is offered.

Source: [standalone `.pak` mod and installation instructions](https://www.nexusmods.com/silenthill2/mods/2).
