---
name: multi-agent-tcp
description: >-
 Work on the current multi_agent_tcp direction: GuLiCode desktop app,
 blueprint runtime control, GraphRuntimeControlPlane, GraphRuntime scheduling,
 top-agent orchestration, AgentNode queues, fan-out/fan-in joins, workspace
 state, events, and CLIWorkerBackend adapters. Use for GuLiCode desktop,
 multi-agent blueprint communication, runtime start/status/end, agent dispatch,
 workspace/archive flow, and legacy TCP/CodeMaker backend compatibility.
---
# multi_agent_tcp - GuLiCode blueprint runtime skill

## Current Position

The current project center is **GuLiCode desktop app + blueprint runtime**.

The main architecture line is:

```text
GuLiCode desktop / UI / top Agent
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace state, events
  -> CLIWorkerBackend
  -> AgentTCPClient / Broker / CLIAdapter / worker process
```

Rules of interpretation:

- Treat `GraphRuntimeControlPlane` and `GraphRuntime` as the current semantic center.
- Treat GuLiCode as the intended top-agent and desktop integration surface.
- Treat low-level TCP workers as a backend adapter path, not the product architecture center.
- Treat `CodeMakerCluster` as a backward-compatible alias for the old cluster facade. New writing should prefer `CLIWorkerBackend` unless explaining legacy APIs.
- Treat Ryven as a legacy/optional visual editor track. Current start decisions belong to GuLiCode/top Agent plans validated by the framework, not to Start/End nodes as decision makers.

Common repository root:

```text
D:\agents\multi_agent_tcp
```

Historical paths such as `F:\src\Package\Script\Python\multi_agent_tcp` or `F:\src\ryven_demo` may appear in archives. Do not use them as current defaults unless the user's machine actually has that path.

## Document Layout

### 1. `SKILL.md`

This file is only the high-level navigation and maintenance policy. Do not put long module details here.

### 2. `多agents通信设计.md`

Primary design document for top-agent governance and multi-agent communication.

Read first when the user asks about:

- GuLiCode as global coordinator / top Agent
- multi-agent communication
- ordinary Agent message dispatch
- start/status/end runtime interfaces
- required outgoing targets
- fan-out and fan-in
- join aggregation
- top-agent rule / skill / profile
- whether Start/End should remain as decision makers

### 3. `knowledge_base/`

Stable current knowledge. Prefer these files for implementation decisions:

- [`knowledge_base/core_architecture.md`](knowledge_base/core_architecture.md): current architecture centered on GuLiCode, `GraphRuntimeControlPlane`, `GraphRuntime`, workspace/events, and CLI backend adapters.
- [`knowledge_base/gulicode_desktop.md`](knowledge_base/gulicode_desktop.md): GuLiCode desktop source structure, Electron/Tauri launch paths, main/preload/renderer/app layering, and desktop integration guidance.
- [`knowledge_base/dispatch_workflows.md`](knowledge_base/dispatch_workflows.md): runtime control-plane CLI/RPC workflows, legacy dispatch notes, and thin-client boundaries.
- [`knowledge_base/ring_structure_solution.md`](knowledge_base/ring_structure_solution.md): ring / 环状结构 / 环审核官 / ring session engineering spec.
- [`knowledge_base/cluster_api.md`](knowledge_base/cluster_api.md): legacy `CodeMakerCluster` compatibility and preferred `CLIWorkerBackend` terminology.
- [`knowledge_base/registry_and_skills.md`](knowledge_base/registry_and_skills.md): registry, skill selection, and catalog injection.
- [`knowledge_base/runtime_notes.md`](knowledge_base/runtime_notes.md): encoding, logs, process cleanup, retry, and CLI runtime pitfalls.
- [`knowledge_base/multi_cli_workflow.md`](knowledge_base/multi_cli_workflow.md): CLI adapter/backend history and still-relevant adapter constraints.
- [`knowledge_base/vendor_ryven_ui.md`](knowledge_base/vendor_ryven_ui.md): vendored Ryven / ryvencore_qt visual-editor knowledge, now secondary.
- [`knowledge_base/agent_node_ryven_integration.md`](knowledge_base/agent_node_ryven_integration.md): Ryven AgentNode wrapper and historical Start/End integration details.
- [`knowledge_base/blueprint_gap_notes.md`](knowledge_base/blueprint_gap_notes.md): UE5 Blueprint comparison notes, useful for UI/editor design only.

### 4. `tasks/`

Short-term work. Prefer current files in this order:

- [`tasks/current_goals.md`](tasks/current_goals.md): current active priorities.
- [`tasks/multi_agent_communication_tasks.md`](tasks/multi_agent_communication_tasks.md): GuLiCode top Agent, runtime control, message staging, joins, and framework-owned communication.
- [`tasks/node_runtime_tasks.md`](tasks/node_runtime_tasks.md): GraphRuntime / graph scheduling implementation tasks.
- [`tasks/multi_cli_adapter_tasks.md`](tasks/multi_cli_adapter_tasks.md): CLI backend adapter work, secondary to runtime/control-plane work.
- [`tasks/vendor_ryven_tasks.md`](tasks/vendor_ryven_tasks.md): Ryven/editor tasks, deferred unless user specifically asks for Ryven.

### 5. `archive/`

Historical change records only. Do not use archive content as current behavior unless a current knowledge document points to it.

- [`archive/agents_architecture_archive.md`](archive/agents_architecture_archive.md)
- [`archive/blueprint_integration_archive.md`](archive/blueprint_integration_archive.md)
- [`archive/gulicode_runtime_baseline_archive.md`](archive/gulicode_runtime_baseline_archive.md)

## Query Map

- GuLiCode desktop startup, Electron/Tauri, desktop source layering: read `knowledge_base/gulicode_desktop.md`.
- GuLiCode 测试环境顶层拉起、aiapi_world/gpt-5.5/provider/baseURL/reasoningEffort 规则: read `knowledge_base/gulicode_desktop.md`.
- GuLiCode top Agent, organization view, top-agent profile, start plan, status explanation: read `多agents通信设计.md`, then `tasks/multi_agent_communication_tasks.md`.
- Runtime start/status/end, organization, message batch, agent dispatch, join-create/join-contribute: read `knowledge_base/dispatch_workflows.md`.
- Current architecture or component ownership: read `knowledge_base/core_architecture.md`.
- `GraphDefinition.agent_cycle_groups()` (exec-edge SCCs, agent-only groups, cycles through `RouteNode`): read `knowledge_base/core_architecture.md` (section *GraphDefinition: agent cycle groups*).
- Ring session / 环状结构 / 环审核官 / dynamic reachable nodes: read `knowledge_base/ring_structure_solution.md`, then `knowledge_base/core_architecture.md` and `knowledge_base/dispatch_workflows.md`.
- Legacy `CodeMakerCluster`, `run_parallel`, `run_chain`, broker/TCP worker path: read `knowledge_base/cluster_api.md`.
- Registry, skills, per-agent skill selection: read `knowledge_base/registry_and_skills.md`.
- Workspace API, changesets, archive, private checkout, conflict flow: read `knowledge_base/core_architecture.md` and `tasks/multi_agent_communication_tasks.md`; use archive only for history.
- Ryven GUI, node visuals, old Start/End wrapper behavior: read `knowledge_base/vendor_ryven_ui.md` and `knowledge_base/agent_node_ryven_integration.md`, but treat them as secondary/deferred.
- Multi CLI adapters, Codex/CodeMaker process adapters, `CLIAdapter`: read `knowledge_base/multi_cli_workflow.md`, but keep the `CLIWorkerBackend` adapter boundary in mind.

## Maintenance Rules

- Current effective knowledge belongs in `knowledge_base/`.
- Short-term priorities and checklists belong in `tasks/`.
- Historical migration notes belong in `archive/`.
- Do not restore old "Cursor/CodeMaker TCP orchestration" framing as the skill center.
- Do not present Ryven Start/End minimum loop as the current product priority unless the user explicitly asks for Ryven/editor work.
- When documenting backend execution, prefer `CLIWorkerBackend`; mention `CodeMakerCluster` only as a compatibility alias.
- When documenting user-facing orchestration, prefer GuLiCode top Agent and framework-owned runtime APIs.
- When copying from `KM_docs/skills-snapshot`, re-check whether imported content reintroduces old center framing before considering the skill clean.

## Repository Link

- GitHub: <https://github.com/QHXRPG-A/multi_agent_tcp>
- Current common local root: `D:\agents\multi_agent_tcp`
