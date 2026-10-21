# Changelog

All notable changes to OmaMods. Versions follow `version` in `pyproject.toml`;
no release has been tagged yet.

History up to and including 0.2.0 was reconstructed from the commit log on
2026-10-21. The commits only mark the bumps to 0.1.1 and 0.2.0; the 0.1.0
boundary below is inferred from what landed just before the 0.1.1 bump
(unverified), and each date is that of the last commit in the range.

## Unreleased

### Added

- `U` (or `:uninstall-all`) uninstalls every mod of a game, from Nexus,
  AyakaMods, and release sources, and keeps going past files it refuses to
  remove, then reports each failure.
- `P` (or `:load-last`) renames an installed Unreal mod's containers so it wins
  asset collisions; the choice survives reinstalls and `:load-default` undoes
  it. RE Engine, REDengine, and ASI loader games are refused.

### Changed

- Uninstalling everything orders reverts so RE Engine patch chains and stacked
  `Engine.ini` copies restore cleanly.

## 0.2.0 - 2026-10-20

### Added

- Warn when two Unreal mods replace the same assets, even inside different
  `.pak` or `.utoc` containers. Collisions show in the inspector and the
  install confirmation, with a prediction of which mod the game will load.

## 0.1.1 - 2026-10-20

### Fixed

- AyakaMods mods with release history list their files again instead of
  reporting none.
- Nexus pages open in their own app window when Omarchy's browser wrapper is
  the default browser.
- A moved checkout no longer leaves the `nxm://` handler pointing at a missing
  program; OmaMods repairs its own handler on startup.

### Added

- `x` removes a download queue entry and `C` (`:clear-all`) clears every entry
  that is not receiving data.

## 0.1.0 - 2026-10-20

First version, developed from 2026-09-16.

### Added

- Read-only discovery of Steam libraries, installs, build IDs, and Proton
  prefixes, plus Heroic (Epic, GOG, Amazon, sideloaded) games; `omamods game
  list` and `omamods inspect <game-id>` on the CLI.
- A Textual terminal UI, opened by a bare `omamods`, that groups games into
  mod-ready, in the catalog, and other installed games, with vim-style keys,
  `/` filtering, `:` commands, inline mod pictures, and a resizable downloads
  panel.
- Nexus Mods staging through the API (Premium), `nxm://` links from the Mod
  Manager Download button, or a manual archive, with a resumable,
  cross-process download queue.
- AyakaMods support: page details, downloads with a saved login cookie, a
  guided login, and a browser fallback that watches the downloads folder.
- Release mods from GitHub and Codeberg, starting with MGSVFix.
- Installers with per-file ownership records and safe revert for Unreal pak
  mods (Cronos, Stellar Blade, MGS Delta, and auto-detected Unreal games),
  RE Engine pak patches (auto-detected, including Fluffy Mod Manager loose
  files), Cyberpunk 2077 mods with their Nexus requirement tree, UE4SS bundles,
  and MGSV ASI plugins.
- Variant pickers for archives that ship alternatives, and packs with several
  loose pak sets.
- RAR5 support through a 7-Zip fallback when `bsdtar` refuses an archive.
- Steam launch-option advice for Cyberpunk, MGS Delta, and MGSV, copied to the
  clipboard or written to Steam's `localconfig.vdf` after a backup, and a
  warning when Cyberpunk's Proton prefix has an old VC++ runtime.
- NSFW handling: pictures blurred by default, `H` cycles blur, hide, and show,
  and `m` marks a mod by hand.
- Live Omarchy theme sync and a redesigned workspace with mod files and artwork
  panes.
- Documentation under `docs/`, the brand mark, the README hero, and the MIT
  license.
