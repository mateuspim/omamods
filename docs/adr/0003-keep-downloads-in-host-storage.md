# 3. Keep downloads and state in persistent host storage

- Status: Accepted
- Documented: 2026-10-20

## Context

A mod archive may outlive an app installation or Distrobox environment. The
TUI and a browser-started `nxm://` process also need a shared location for
staged files and queue status. Different sites can reuse the same numeric IDs.

## Decision

Use an XDG-based host storage root, configurable with `[storage] root`.
Stage Nexus archives by game, mod ID, and file ID. Keep install records and
queue status under the same root. Give AyakaMods and release mods their own
namespaces. Store credentials separately in a private config file.

## Consequences

- Browser handler and TUI can coordinate through persisted files.
- Removing or moving storage without its game files breaks safe revert.
- Site numbering cannot collide across the separate namespaces.

See `src/omamods/nexus_config.py`, `src/omamods/staging.py`, and
`src/omamods/download_queue.py`.
