# Glossary

| Term | Meaning in OmaMods |
| --- | --- |
| Adapter | Game-specific discovery or install behavior. A manifest's `adapter` describes a proposed family; it does not guarantee an installer. |
| Catalog | Versioned `games/<id>/game.yml` declarations and game notes in this repository. |
| Mod-ready | A discovered game for which OmaMods currently has an installer path. |
| Staging | Persistent host storage for downloaded archives and page metadata before install. |
| Variant | A selectable folder or option within an archive; choices can be mutually exclusive when they target the same files. |
| Ownership record | JSON state naming a mod file's installed targets and hashes, used to decide what revert may remove or restore. |
| Revert | Remove files owned by one staged file or mod, subject to its recorded state and safety checks. |
| Steam app ID | Stable numeric Steam identifier used to match a catalog entry to an installation. |
| Steam build ID | Steam metadata about an installation, not proof of its executable version or mod compatibility. |
| Proton prefix | Windows-like environment Steam uses for a Windows game under Proton; some loader settings live there. |
| NXM | `nxm://` link from Nexus' Mod Manager Download action, passed to OmaMods by a registered desktop handler. |
| IoStore | Unreal asset layout commonly using related `.pak`, `.ucas`, and `.utoc` files. |
| RE Engine patch chain | Numbered `re_chunk_000.pak.patch_NNN.pak` files (or a `sub_000` variant) loaded in sequence by supported Capcom games. |
| KPKA | RE Engine `.pak` archive format; supported Fluffy-style loose files can be packed into a patch. |
| XDG | Linux directory convention used for private config and persistent app data. |
