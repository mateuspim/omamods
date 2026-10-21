# OmaMods documentation

## Use OmaMods

- [Using the terminal UI](using-the-tui.md): screen layout, keys, downloads,
  themes, and AyakaMods.
- [Game workflows](game-workflows.md): supported archive formats and CLI
  installation paths.
- [Game discovery](discovery.md): read-only Steam inspection.
- [Configuration and storage](configuration.md): private settings and records.
- [Troubleshooting and recovery](runbooks/troubleshooting.md).
- [Glossary](glossary.md).
- [Security and privileges](../SECURITY.md).
- [Changelog](../CHANGELOG.md).
- [Brand assets](branding.md): icon, wordmarks, and README hero.

## Develop OmaMods

- [Architecture](architecture.md): boundaries and data flow.
- [Architecture decisions](adr/README.md): durable tradeoffs.
- [Game manifest specification](specs/game-manifest.md).
- [Profile workflow proposal](specs/profile-workflow.md): future profile commands and required safeguards.
- [Development runbook](runbooks/development.md).
- [Contributing](../CONTRIBUTING.md) and [agent instructions](../AGENTS.md).

Game-specific constraints are in each [`games/<id>/README.md`](../games/).
Catalog discovery and mod installation are separate capabilities: a visible
game is not automatically mod-ready.
