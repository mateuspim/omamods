# 4. Inject host operations into the TUI service

- Status: Accepted
- Documented: 2026-10-20

## Context

The terminal workspace needs network requests, archive reads, browser
launches, Steam integration, theme colors, and filesystem access. Coupling
screens directly to those resources would make behavior hard to test without
using a real game library or account.

## Decision

Screens call `ModsService`. `TuiHost` provides explicit adapters for external
operations, and project-owned wrappers isolate third-party libraries.
Headless tests supply named fake transports, readers, launchers, and shelves.

## Consequences

- UI behavior can be tested without touching live Steam or credentials.
- New host integrations belong behind an injected adapter.
- Screens remain focused on presentation and command dispatch.

See `src/omamods/tui/service.py`, `src/omamods/host_cli.py`, and
`tests/fakes.py`.
