# multi_agent_tcp knowledge base index

This directory stores current effective knowledge for the `multi-agent-tcp` skill.

Current architecture priority:

```text
GuLiCode desktop / top Agent
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, fan-out batches, fan-in joins, workspace/events
  -> CLIWorkerBackend adapter path
```

Historical TCP / CodeMaker / Ryven information may still be useful, but it is no longer the center of the project.

## Current Modules

- `core_architecture.md`: current architecture, ownership boundaries, and how GuLiCode, runtime control, graph scheduling, workspace, events, and CLI backend adapters fit together. Includes **`GraphDefinition.agent_cycle_groups()`** (exec-edge SCCs, agent-only cycle groups).
- `gulicode_desktop.md`: GuLiCode desktop source structure, Electron/Tauri startup, main/preload/renderer/app layering, and desktop integration path.
- `dispatch_workflows.md`: current GraphRuntimeControlPlane CLI/RPC workflows plus legacy dispatch notes.
- `registry_and_skills.md`: `agents_registry.json`, skill selection, skill injection, and registry workflow.
- `runtime_notes.md`: encoding, logs, process cleanup, heartbeats, retries, and CLI runtime pitfalls.
- `cluster_api.md`: `CLIWorkerBackend` / legacy `CodeMakerCluster` compatibility API.
- `multi_cli_workflow.md`: CLI adapter/backend history and still-relevant adapter constraints.
- `vendor_ryven_ui.md`: vendored `ryvencore_qt` / Ryven visual-editor knowledge. Secondary unless the task is explicitly about Ryven.
- `agent_node_ryven_integration.md`: Ryven AgentNode wrapper and historical Start/End behavior. Secondary/deferred.
- `blueprint_gap_notes.md`: UE5 Blueprint comparison notes for future editor/UI design.

## Rules

- Keep current behavior here.
- Put short-term work in `../tasks/`.
- Put historical transitions in `../archive/`.
- If a document still says CodeMakerCluster/TCP/Ryven is the main product direction, update or clearly mark it as legacy.
