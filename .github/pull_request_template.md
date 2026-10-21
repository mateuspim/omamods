## What and why

<!-- One or two sentences. Link the issue. -->

## Checklist

- [ ] `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` passes
- [ ] `python -m black --check src tests` is clean
- [ ] Docs, game README, and CHANGELOG (Unreleased) updated where behaviour changed
- [ ] ADR added for a durable design choice
- [ ] No personal paths, Steam data, credentials, or archives; captures use fake data
