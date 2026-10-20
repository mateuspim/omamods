# Configuration and storage

OmaMods keeps credentials, downloads, and ownership state outside Git. The
private config defaults to `~/.config/omamods/config.toml` (or
`$XDG_CONFIG_HOME/omamods/config.toml`). Run `omamods config init` to create it
with mode `0600`. The TUI can save the Nexus API key with `K`.

Persistent storage defaults to `~/.local/share/omamods` (or
`$XDG_DATA_HOME/omamods`). Set an absolute `[storage] root` in the config to
move it. Keep this directory on the host and back it up with the game files it
tracks. A removed storage directory loses the ownership records needed for a
safe revert.

```toml
[nexus]
api_key = ""

[storage]
root = "/path/to/persistent/omamods"

# Optional for a game with several Steam installations:
# [games.cronos]
# install_dir = "/path/to/Cronos. The New Dawn"
```

`NEXUS_API_KEY` is also accepted by the CLI. The personal key is for Nexus
requests; release downloads use their own anonymous transport. AyakaMods can
save an `xf_user` login cookie in the same private config; treat it as a
password. See [the AyakaMods workflow](using-the-tui.md#ayakamods).

## What is stored

| Path under storage root | Purpose |
| --- | --- |
| `archives/<game>/<mod-id>/` | Nexus page metadata, picture, and downloaded files by file ID. |
| `state/<game>/<mod-id>/` | Per-file records (`<file-id>.json`) and variant records (`<file-id>.<digest>.json`). |
| `state/<game>/<mod-id>.json` | Older per-mod records, still readable and revertible. |
| `state/<game>/<mod-id>/*.config.json` and `*.config.originals/` | UE4SS prefix configuration records and saved originals. |
| `state/<game>/<mod-id>/<file-id>[.<digest>].load-order` | Containers renamed to load last (`P`), reapplied on reinstall. |
| `state/requirement_chain.json` | In-progress Nexus requirement installation chain. |
| `backups/steam-localconfig/` | Copies made before writing Steam launch options. |
| `downloads/` | Cross-process queue status for the TUI and browser handler. |
| `cache/nexus_games.json` | Cached Nexus game mapping for auto-detection. |
| `detected_games.json` | Last detected games for the separate NXM process. |
| `adult_marks.json` | Hand-marked adult content and visibility setting. |
| `ayaka/`, `release/` | Separate staging and records for sources with their own mod IDs. |
| `logs/nxm.jsonl` | JSON-lines browser-handler diagnostics. |

Some installs also set aside an original file or back up Steam's
`localconfig.vdf` before a launch-options change. These paths are part of the
recovery chain: do not hand-delete them while the corresponding mod is
installed. For inspection and recovery, see [the runbook](runbooks/troubleshooting.md).

## CLI overrides

`--config /absolute/path/config.toml` selects another private config for
write-capable commands. `--games-dir` selects a catalog and repeated
`--steam-root` arguments replace automatic Steam-root discovery. Put global
options before the command:

```sh
omamods --games-dir /path/to/catalog --steam-root /path/to/Steam inspect dawnwalker
```

The catalog and source archives are separate: putting a game manifest in Git
does not store its downloaded mods there. Never commit credentials, staged
archives, install state, or real machine paths.
