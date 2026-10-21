# Development runbook

## Prepare a checkout

Use `master` as the default branch. OmaMods requires Python 3.12 or newer.
From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

The project uses a `src/` layout. Run every test through the documented
command:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Format code with `python -m black src tests`. CI
([`.github/workflows/test.yml`](../../.github/workflows/test.yml)) runs the
same tests on Python 3.12 and `black --check src tests`; report the exact local
command and result with a change.

## Make a game change

1. Update `games/<id>/game.yml` and the game's README for discovery or
   compatibility facts. Use the [manifest spec](../specs/game-manifest.md).
2. If installation changes, update the focused archive planner and record
   logic. Cover accepted layout, rejected layout, collision, and revert with
   named fake host adapters and a regression test for any fixed bug.
3. Update [game workflows](../game-workflows.md) and the TUI guide if controls
   change. Put a durable design tradeoff in an [ADR](../adr/README.md).
4. Run the test command, then inspect `git diff --check` and `git status`.

A manifest alone is insufficient to enable installation. Keep new installers
behind the `ModsService`/`TuiHost` boundary and leave live Steam, game, and
browser state out of tests.

## Refresh the preview

The README hero is `docs/preview.png`. Its editable layout is
`docs/preview.svg`; it places two headless Textual/Rich captures from a fake shelf:
`docs/assets/library.png` and `docs/assets/workspace.png`. The fixtures in
`tests/test_tui.py` supply sample games and mod files. Rich adds the decorative
window title bars and coloured dots during SVG export; they are not desktop
windows. Never use the live game library, personal credentials, or a desktop
screenshot.

After updating the captures or layout, inspect both the source images and the
rendered result. Replace temporary fixture paths in captures with sample paths
before committing. The current image was rendered with librsvg 2.63.3 on a
system where Fontconfig substitutes Liberation Sans for the requested DejaVu
Sans and JetBrains Mono Nerd Font for DejaVu Sans Mono. Other font setups can
change text spacing; inspect the output after rendering. Render the 3840 ×
2160 PNG with:

```sh
rsvg-convert -o docs/preview.png docs/preview.svg
```

Keep the README alt text accurate.

## Release

Ask the owner before tagging or pushing.

1. Bump `version` in `pyproject.toml` and refresh `uv.lock` (`uv lock`).
2. Move the `CHANGELOG.md` Unreleased entries under `## X.Y.Z - YYYY-MM-DD`.
3. Check the README and the guides in `docs/` cover the change.
4. Run the tests and `python -m black --check src tests`.
5. Commit `Release X.Y.Z`; after the owner approves, add an annotated tag
   `vX.Y.Z`.
