# Current Short-Term Goals

Last cleaned: 2026-05-09

## Current Main Line

The active project direction is:

```text
GuLiCode desktop / top Agent
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace/events
  -> CLIWorkerBackend adapters
```

Primary design source:

- [`../多agents通信设计.md`](../多agents通信设计.md)
- [`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)
- [`../knowledge_base/gulicode_desktop.md`](../knowledge_base/gulicode_desktop.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)

## Recently Completed Runtime Capabilities

- Framework-owned one-to-many outgoing message staging.
- Complete-batch dispatch into downstream Agent queues.
- `remaining_targets` reminders when source Agents return to `idle`.
- Graph-derived `agent_connections`.
- Organization view with top/full and scoped ordinary-agent variants.
- GuLiCode top-agent profile, rule/skill skeleton, start-plan validation, and top-agent context rendering.
- Runtime start/status/end basics through `GraphRuntimeControlPlane`, RPC, and CLI thin clients.
- `agent.dispatch` wrapper for ordinary-Agent downstream messages.
- Join barriers for fan-in: `wait-all`, `wait-any`, `quorum`, and `timeout`.
- Join aggregate envelope queueing into target Agent queues.
- Cancel/fail cleanup for pending runtime work.
- Sequential DAG runner with automatic multi-input fan-in.
- Final report generation and archive indexing on completion.

## Active Priorities

1. Wire the non-UI control plane into a real long-lived GuLiCode/top-Agent session.
2. Bind ordinary-Agent message dispatch to current task envelopes and `required_outgoing_targets`.
3. Inject ordinary-Agent rule / skill / tool context into AgentNode startup context.
4. Continue hardening status explanation and event summaries for GuLiCode/top Agent and UI.
5. Connect GuLiCode desktop UI to runtime/control-plane state without duplicating scheduling semantics.
6. Keep workspace/archive behavior aligned with framework-owned changeset, conflict, report, and artifact records.

## Deferred / Secondary Tracks

### CLI backend adapters

Continue maintaining Codex/CodeMaker adapters and `CLIWorkerBackend`, but do not let adapter mechanics drive product architecture.

See [`multi_cli_adapter_tasks.md`](multi_cli_adapter_tasks.md).

### Ryven / visual editor

Ryven remains useful as a visual editor and historical prototype, but the current control model is GuLiCode/top-Agent start plans validated by the framework. Do not treat `Start -> AgentNode -> End` as the main product priority unless the user explicitly asks for Ryven/editor work.

See [`vendor_ryven_tasks.md`](vendor_ryven_tasks.md).

### Old CodeMakerCluster/TCP docs

The TCP worker path remains as backend compatibility. New docs should say `CLIWorkerBackend`; use `CodeMakerCluster` only for legacy API compatibility.

## Validation Snapshot

Most recent project validation observed during cleanup/update:

```text
python -m pytest
103 passed
```

Re-run tests after code changes, especially changes touching `graph_runtime.py`, `graph_control.py`, workspace APIs, or backend adapters.
