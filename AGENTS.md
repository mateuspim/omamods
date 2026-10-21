# OmaMods contributor guide

OmaMods is a Python 3.12+ Textual application. Read the relevant user guide and
[architecture](docs/architecture.md) before changing a workflow. Keep the
README short; put detailed usage in `docs/` and game-specific rules in
`games/<id>/README.md`.

## Git and scope

- Always use `master` as the default branch. Never assume, create, switch to,
  or recreate `main`. Base new work from `master`.
- Preserve user-created files and local state. `docs/mod-manager-architecture.html`
  may be an untracked working draft; do not overwrite it without a task that
  explicitly calls for it.
- `HANDOFF.md` is local-only and stays gitignored.
- Do not put credentials, downloaded archives, personal paths, or Steam data in
  tracked files. Use fake library data for screenshots and examples.

## Architecture

- CLI entry: `src/omamods/cli.py`; host wiring: `host_cli.py` and
  `nexus_cli.py`; TUI screens: `src/omamods/tui/`.
- Discovery uses `games/<id>/game.yml` and read-only filesystem adapters.
  A manifest does not enable an installer. See the [manifest spec](docs/specs/game-manifest.md).
- TUI screens call `ModsService` through an injected `TuiHost`. Keep network,
  filesystem, archive, browser, and Steam operations behind project-owned
  interfaces. Inject dependencies through constructors or parameters, never
  globals or imports. See [architecture](docs/architecture.md) and
  [ADRs](docs/adr/README.md).
- Keep archives and install records in the configured host storage root.
  Preflight target paths, record ownership, and preserve revert behavior when
  changing an installer. See [storage](docs/configuration.md).

## Code style

- Functions: 4–20 lines. Split longer functions. Files: under 500 lines.
- One thing per function and one responsibility per module. Use specific,
  greppable names (prefer fewer than five codebase hits); avoid generic
  `data`, `handler`, and `Manager` names.
- Use explicit types: no `any`, `Dict`, or untyped functions. Follow the
  framework conventions in use. Extract shared logic instead of duplicating it. Prefer early returns and at most two
  indentation levels.
- Exception messages include the offending value and expected shape.
- Preserve existing comments in refactors. New comments explain why, and
  mention an issue or commit when a line exists for that constraint.
- Public functions need docstrings with intent and one usage example.

## Tests and formatting

- Run all tests with `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`.
  Create `.venv` and install `.[dev]` as shown in the README if needed.
- Every new function gets a test; bug fixes get a regression test. Use named
  fake classes for external I/O. Tests stay fast, independent, repeatable,
  self-validating, and timely.
- Format with `python -m black src tests`.
- Use structured JSON for diagnostic logs and plain text for user-facing CLI
  output.

## Documentation changes

- Update the focused guide when behavior changes; update the README only when
  the entry point or project summary changes.
- Add an ADR for a durable design choice, with context, decision, and
  consequences. Update the index in `docs/adr/README.md`.
- Check relative links and examples against the implementation. Keep any
  screenshot based on fake data, never the user's live desktop.

## Commits and releases

- Commit subjects are plain imperative sentences with a body that says why.
  Ask the owner before pushing commits or tags, and before publishing a
  GitHub release.
- Release: bump `version` in `pyproject.toml` (and `uv.lock`), add the
  `CHANGELOG.md` entry, check the README and `docs/` cover the change, run the
  tests and `black --check src tests` (CI runs the same), commit
  `Release X.Y.Z`, then add an annotated tag `vX.Y.Z` only after the owner
  approves. See the [development runbook](docs/runbooks/development.md#release).
