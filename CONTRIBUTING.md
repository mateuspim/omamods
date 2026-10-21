# Contributing to OmaMods

Thanks for helping. OmaMods is a small project; issues and focused pull
requests are welcome.

## Before you start

- Bugs and ideas: open an issue first for anything larger than a small fix.
- Security problems: follow [SECURITY.md](SECURITY.md), not a public issue.
- Read [AGENTS.md](AGENTS.md): it holds the code rules for people and coding
  agents alike, and [docs/architecture.md](docs/architecture.md). The
  [documentation index](docs/README.md) lists the rest.

## Set up

OmaMods needs Python 3.12 or newer. From a clone of
`https://github.com/mateuspim/omamods`:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
omamods
```

Install `bsdtar` (and `7z` for some RAR5 archives) to install real mods. The
tests do not need them. The [development runbook](docs/runbooks/development.md)
has the full workflow.

## Make a change

1. Branch from `master`.
2. Keep the change focused; update the guide in `docs/` (or the game's
   `games/<id>/README.md`) that the change affects.
3. Add or update tests with named fakes for external I/O; tests never touch
   real Steam libraries, game folders, or the network. Run:

   ```sh
   PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
   python -m black src tests
   ```

4. For UI changes, attach a headless capture from test fixtures (see the
   [development runbook](docs/runbooks/development.md)), never a desktop
   screenshot with your games or credentials.
5. Durable design choice? Add an ADR under [docs/adr](docs/adr/README.md).

## Commit style

Plain imperative subject ("Add …", "Keep …"), under ~72 characters, and a
body that explains why.

## Pull request checklist

- [ ] Tests pass and `black --check src tests` is clean
- [ ] Docs and CHANGELOG (Unreleased) updated
- [ ] No personal paths, Steam data, credentials, or archives in tracked files

## License

By contributing you agree your work is released under the [MIT License](LICENSE).
