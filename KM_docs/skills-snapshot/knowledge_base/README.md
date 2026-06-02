# multi_agent_tcp knowledge base index

This directory stores current effective knowledge for the `multi-agent-tcp` skill.

Current architecture priority:

```text
GuLiCode desktop / top Agent
  -> Guli productization and blueprint workbench entry
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, fan-out batches, fan-in joins, workspace/events
  -> CLIWorkerBackend adapter path
```

Historical TCP / Codex information may still be useful, but it is not the center of the project. The old Ryven/editor UI track has been removed from the active skill snapshot.

## Current Modules

- `core_architecture.md`: current architecture, ownership boundaries, and how GuLiCode, runtime control, graph scheduling, workspace, events, and CLI backend adapters fit together. Includes **`GraphDefinition.agent_cycle_groups()`** (exec-edge SCCs, agent-only cycle groups).
- `gulicode_desktop.md`: GuLiCode desktop source structure, Electron/Tauri startup, one-click packaged launch, main/preload/renderer/app layering, and desktop integration path.
- `guli_desktop_ui.md`: Guli productization, desktop UI ownership, branding surfaces, icon pipeline, blueprint entry embedding, and workbench integration rules.
- `dispatch_workflows.md`: current GraphRuntimeControlPlane CLI/RPC workflows plus legacy dispatch notes.
- `ring_structure_solution.md`: ring / 环状结构 handling under the current runtime semantics.
- `registry_and_skills.md`: `agents_registry.json`, skill selection, skill injection, and registry workflow.
- `runtime_notes.md`: encoding, logs, process cleanup, heartbeats, retries, and CLI runtime pitfalls.
- `cluster_api.md`: `CLIWorkerBackend` / legacy `CLIWorkerBackend` compatibility API.
- `multi_cli_workflow.md`: CLI adapter/backend history and still-relevant adapter constraints.

## Rules

- Keep current behavior here.
- Put short-term work in `../tasks/`.
- Put historical transitions in `../archive/`.
- If a document still says CLIWorkerBackend/TCP is the main product direction, update or clearly mark it as legacy.
- If a task tries to restore Ryven/editor as the current UI center, treat it as a deliberate direction change that must be explicitly requested by the user.
