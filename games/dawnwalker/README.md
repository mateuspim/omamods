# The Blood of Dawnwalker adapter

This is the first OmaMods game adapter. It is intentionally a discovery-only
placeholder until the game has a released Linux/Proton modding workflow and
specific mod sources to support.

The adapter will answer these questions before any installer is written:

1. Which Steam app ID and executable version are installed?
2. Does the game use loose-file overlays, an Unreal Engine loader, a dedicated
   manager, or its own mod interface?
3. Which files belong in the game directory and which belong in the Proton
   prefix?
4. How can each change be backed up and reverted?

No mods or loaders are assumed by this repository yet.
