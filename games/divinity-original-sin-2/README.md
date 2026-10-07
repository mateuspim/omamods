# Divinity: Original Sin 2 adapter

Steam app ID: `435150`. Inspect the local installation with
`omamods inspect divinity-original-sin-2`.

The Steam Workshop and the game's own mod selection make this a straightforward
manual modding path. The installed game includes Definitive Edition. Subscribe
to a mod through Steam, then check whether it appears in the game's Mods menu
before enabling it. Some Workshop subscriptions may need the `.pak` copied
from Steam's Workshop cache to the game's Documents mod directory, which is
inside the Proton prefix on Linux. Choose the mod's Definitive Edition version
where offered.

OmaMods does not yet synchronize Workshop subscriptions, edit the game's
profile state, or impose a load order. A reproducible profile will need exact
Workshop item versions, dependencies, enabled state, and order. We should
inspect how the game records those before implementing any write operation.

Sources: [Steam Workshop](https://steamcommunity.com/app/435150/workshop/),
[Larian's modding documentation](https://docs.larian.game/My_first%3A_Add-on),
[Definitive Edition guidance](https://docs.larian.game/Definitive_Edition),
[Workshop installation troubleshooting](https://steamcommunity.com/sharedfiles/filedetails/?id=2097784116).
