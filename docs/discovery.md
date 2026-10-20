# Game discovery

Requires Python 3.12 or newer. From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
omamods game list
omamods inspect dawnwalker
omamods inspect silent-hill-2
```

If Python and PyYAML are already installed, you can also run without installing
the package:

```sh
PYTHONPATH=src python -m omamods inspect dawnwalker
```

`game list` lists games declared in this repository, with their local installation
status. `inspect` reports discovered libraries and, for games with a configured
Steam app ID, game directories, Steam build IDs, installation flags, and existing
Proton prefixes. A Steam build ID is metadata, not a verified executable version.
Neither command writes to Steam, game directories, or Proton prefixes.

## How Steam matching works

OmaMods looks for native Steam under `XDG_DATA_HOME/Steam`, `~/.steam/steam`,
and `~/.steam/root`, and for Flatpak Steam under
`~/.var/app/com.valvesoftware.Steam/.local/share/Steam`. It reads modern
nested and older string-path entries in `steamapps/libraryfolders.vdf` and
deduplicates symlink aliases. Each catalog game with a Steam app ID matches
only `steamapps/appmanifest_<id>.acf`; it is never matched by title. Missing,
unreadable, or malformed manifests produce warnings or partial results.

The game directory must exist and Steam's installed flag must be set before a
match counts as installed. The CLI reports every matching library copy. It
does not verify game files, executable version, or mod compatibility.

| Inspection status | Meaning |
| --- | --- |
| `app-id-unconfigured` | The catalog game has no Steam app ID, so matching cannot start. |
| `installed` | At least one match has its game directory and Steam's installed flag. |
| `incomplete-install` | Matching metadata exists, but no match meets both conditions. |
| `discovery-incomplete` | No match was found, and warnings prevented a clean search. |
| `not-found` | No match was found in an accessible library without warnings. |

## CLI overrides and exit codes

For custom locations, put global options before the command:

```sh
omamods --games-dir /path/to/omamods/games --steam-root /path/to/Steam inspect dawnwalker
```

`--games-dir` uses `./games` when present, then falls back to this
checkout's `games/` directory.
Repeat `--steam-root` for multiple clients; explicit roots replace automatic
root discovery. Missing game installations and unconfigured app IDs are normal
results. Exit codes are `0` for a completed inspection, `1` for partial results
with discovery warnings, and `2` for invalid input or unreadable catalog files.

