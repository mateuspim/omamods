# Architecture decision records

These records explain implemented design choices. They were documented from
the current code on 2026-10-20; their date is a documentation date, not a claim
about when the original change landed. For the current component map, see the
[architecture overview](../architecture.md).

| # | Decision | Status |
| --- | --- | --- |
| [1](0001-separate-discovery-from-install-support.md) | Separate game discovery from install support | Accepted |
| [2](0002-record-ownership-for-revert.md) | Record file ownership for safe revert | Accepted |
| [3](0003-keep-downloads-in-host-storage.md) | Keep downloads and state in persistent host storage | Accepted |
| [4](0004-inject-host-operations-into-tui-service.md) | Inject host operations into the TUI service | Accepted |
| [5](0005-predict-unreal-asset-load-order.md) | Predict Unreal asset load order from container names | Accepted |

Add the next number for a new durable choice. Include context, decision, and
consequences. When replacing a decision, mark the old record superseded and
link the new one rather than rewriting history.
