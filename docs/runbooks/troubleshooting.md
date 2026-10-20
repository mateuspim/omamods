# Troubleshooting and recovery

Start with the game's [adapter notes](../../games/) and the
[game workflows](../game-workflows.md). Close the game before changing mod
files. The TUI's `w` on the home screen shows discovery warnings; `D` opens
the download queue. The `nxm://` handler logs JSON lines under
`<storage-root>/logs/nxm.jsonl`.

## `omamods` cannot import the package

An editable install stores the checkout's absolute `src/` path. If the repo
moves, a launcher can remain on `PATH` while its package path is stale. From
the current repository root, repair a uv tool install with:

```sh
uv tool install --editable --reinstall .
```

If you run through this checkout's virtual environment, activate it and run
`python -m pip install -e '.[dev]'` again. Verify with `omamods --help` and
`omamods game list`. A stale `.pth` path under the tool or virtual environment
is the cause when those commands fail with `ModuleNotFoundError` for `omamods`.

## A game is missing or not mod-ready

1. Run `omamods game list` and `omamods inspect <catalog-id>`. Check warnings
   for inaccessible Steam libraries or malformed metadata. The CLI does not
   modify Steam or the game.
2. Confirm the install is fully installed in Steam or visible to Heroic. Use
   `r` on the home screen to rescan. A catalog entry is not itself an installer.
3. For a detected Unreal or RE Engine game, check that its game layout matches
   the detector and that OmaMods can match the title to Nexus. Its cached game
   mapping is under `<storage-root>/cache/nexus_games.json`.

## A download is waiting or failed

- Nexus non-Premium downloads require a browser click on **Mod Manager
  Download** after `n` registers the NXM handler. In the queue, `r` retries a
  selected failed or stalled item; `c` clears finished entries.
- AyakaMods may need a fresh login cookie or a manual browser download into
  the system Downloads folder. The TUI waits for one browser download at a
  time; `:stop` cancels that wait.
- Confirm the storage root is writable and has room. Inspect the queue and
  `nxm.jsonl` for the actual file ID and error. Avoid copying a different
  archive into an existing staged file's path.

## An install is refused

- Read the target paths shown before the write. A target owned by another mod
  or an unrelated existing file is a collision. Revert the owning mod first,
  or choose a different variant; do not delete a game file blindly.
- An archive containing unsupported loaders, scripts, or package formats may
  need a different adapter. Check the game's README for supported layouts.
- For RE Engine, game updates can replace a numbered mod patch. OmaMods may
  then refuse removal of the changed file. Reinstall mods against the updated
  game, preserving the old storage root until records are reconciled.

## Revert or repair state

1. Back up the game directory, private config, and full storage root together
   before manual repair. The ownership record links a staged archive to actual
   target files; keep them paired.
2. Use the TUI's `u` or CLI `omamods nexus revert <game-id> <mod-id>` for a
   supported Nexus CLI game. Add `--file-id` to target one staged file.
3. If revert reports a changed target, inspect the named path and record under
   `<storage-root>/state/` before changing anything. A hash mismatch protects
   local edits or game updates from deletion. Original prefix files and Steam
   launch-options backups may need separate restoration.
4. Re-run `omamods inspect <game-id>` and rescan the TUI after recovery. Keep
   the archive and state backup until the game starts with the intended mods.

Never publish the private config, a login cookie, personal paths, or diagnostic
logs containing download links in an issue report.
