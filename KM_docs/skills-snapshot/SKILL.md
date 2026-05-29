---
name: multi-agent-tcp
description: >-
 Work on the current multi_agent_tcp direction: GuLiCode desktop productization,
 blueprint runtime embedding, GraphRuntimeControlPlane, GraphRuntime scheduling,
 top-agent orchestration, AgentNode queues, workspace state, events, and
 CLIWorkerBackend adapters. Use for GuLiCode desktop, blueprint entry embedding,
 runtime start/status/end, agent dispatch, workspace/archive flow, per-agent
 private workspaces, MCP workspace tools, and legacy TCP/CodeMaker compatibility.
---
# multi_agent_tcp Project Skill

Use this skill when working on the `multi_agent_tcp` repository, especially the
GuLiCode desktop app, blueprint runtime, top-agent orchestration, multi-agent
communication, workspace isolation, MCP workspace tools, and CLI worker
adapters.

This file is intentionally short so Codex can discover the skill reliably.
Detailed context lives in the files listed below. Load only the relevant files
for the current task.

## Current Center

The active product direction is:

```text
GuLiCode desktop / UI / top Agent
  -> blueprint entry and workbench surfaces
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace state, events
  -> CLIWorkerBackend
  -> AgentTCPClient / Broker / CLIAdapter / worker process
```

Interpretation rules:

- Treat GuLiCode desktop as the user-facing product center.
- Treat blueprint capability as embedded inside GuLiCode desktop, not as a
  separate Ryven-led product surface.
- Treat `GraphRuntimeControlPlane` and `GraphRuntime` as the framework-owned
  execution center.
- Treat low-level TCP workers as a backend adapter path, not the product
  architecture center.
- Prefer `CLIWorkerBackend` in new writing. Mention `CodeMakerCluster` only as a
  backward-compatible alias for the old cluster facade.
- Keep Codex-first adapter work as the default for live blueprint smoke,
  streaming, and MCP workspace-tool validation.
- Do not revive the retired Ryven/editor UI line unless the user explicitly asks
  for it.

Current common local root:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

Historical paths such as `D:\agents\multi_agent_tcp` may appear in archive
notes. Do not use them as current defaults unless they exist on this machine.

## Start Here

Read these first based on the task:

- Project architecture and ownership:
  `knowledge_base/core_architecture.md`
- GuLiCode desktop startup, packaging, and shell/runtime layering:
  `knowledge_base/gulicode_desktop.md`
- GuLiCode UI, blueprint side panel, workbench entry, branding, and renderer
  conventions:
  `knowledge_base/guli_desktop_ui.md`
- Runtime control-plane CLI/RPC flows:
  `knowledge_base/dispatch_workflows.md`
- Top-agent governance and multi-agent communication design:
  `多agents通信设计.md`
- Registry, skill selection, and skill injection:
  `knowledge_base/registry_and_skills.md`
- CLI adapter/backend history and constraints:
  `knowledge_base/multi_cli_workflow.md`
- Environment setup and machine-specific diagnostics:
  `environment_setup.md`
- Current active priorities:
  `tasks/current_goals.md`
- Debug start workflow for desktop + Collaboration Server + mock mobile +
  server console:
  `knowledge_base/debug_start.md`

## Recent Handoff

For the latest Blueprint Agent model/runtime cleanup from 2026-05-29:

- Test Agent merge into normal Agent UI, global Agent panel JSON test-log
  switch, Agent `简介` / `提示词` split, and frontend tests:
  `archive/frontend/blueprint_agent_prompt_log_cleanup_2026-05-29.md`
- Hidden Windows worker/adapter launches and per-run `run_prompt` runtime
  injection:
  `archive/runtime-backend/blueprint_hidden_console_run_prompt_2026-05-29.md`

Use those files when the user reports:

- Test Agent nodes or yellow test styling still appear in the Blueprint UI
- Agent panel test JSON snapshots are missing, unexpectedly produced, or need
  the global switch behavior checked
- Agent inspector `简介` / `提示词` behavior is unclear
- Blueprint startup opens visible terminal windows
- `run_prompt` is injected repeatedly or not injected on first dispatch

For the latest Collaboration Server `/mobile` desktop-bridge work from
2026-05-29:

- Account-level desktop bridge, mobile chat, composer mode sync, structured
  segments, and tick/scroll fixes:
  `archive/future-server/collaboration_server_desktop_bridge_mobile_chat_2026-05-29.md`

Use that file when the user reports:

- mobile chat send reaches desktop but does not appear on `/mobile`
- `/mobile` mode selector is missing desktop agents or `蓝图规划`
- reasoning/tool disclosures close, resize, or jump scroll during tick refresh
- desktop session mirror or `desktop.session.submit` behavior is unclear

For the latest blueprint panel work from 2026-05-25:

- Progress overlay and staged-plan sync:
  `archive/frontend/blueprint_flow_progress_overlay_plan_sync_2026-05-25.md`
- Runtime visual flow and pending filter:
  `archive/frontend/blueprint_runtime_visual_flow_pending_filter_2026-05-25.md`

Use those files when the user reports:

- blueprint submit progress is missing or stuck
- the Top Agent plan card does not appear
- the blueprint panel overlay/mask behavior is wrong
- runtime node glow, edge flow, or pending task filtering looks wrong

## Archive Structure

Archive records are split by ownership:

- `archive/frontend/`: GuLiCode renderer/app UI, blueprint side panel, session
  composer planning UX, CSS/i18n, popout windows, and UI tests.
- `archive/runtime-backend/`: GraphRuntime, GraphRuntimeControlPlane, Blueprint
  MCP runtime, DesktopBlueprintService, AgentTCP, CLIWorkerBackend, queues,
  workspaces, and local desktop service behavior.
- `archive/future-server/`: reserved for future hosted/server-side product work.

Archives are historical records. Prefer current `knowledge_base/` and `tasks/`
files for implementation decisions unless an archive is explicitly called out.

## Query Map

- Local environment setup, Python/Bun/Codex paths, PowerShell script policy,
  localhost MCP `502` / `503`, proxy, `NO_PROXY`, and repo `skill_list`:
  read `environment_setup.md`.
- GuLiCode startup, one-click launcher, packaged bring-up, taskbar icon, and
  direct Electron fallback: read `knowledge_base/gulicode_desktop.md`.
- When the user says `调试启动`: read `knowledge_base/debug_start.md`, then
  start GuLiCode desktop, the Collaboration Server, the mock mobile `/mobile`
  client, and the `/console` server console.
- Desktop UI ownership, branding, icon replacement, empty-state wording,
  blueprint entry placement, and blueprint workbench embedding:
  read `knowledge_base/guli_desktop_ui.md`, then
  `tasks/guli_desktop_ui_tasks.md`.
- Agent information panel interactions, task status display, automatic Top
  Agent summary, long-press progress, Markdown reply rendering, context menu,
  move/resize behavior, Test Agent JSON snapshots, and clean desktop debug:
  read `archive/frontend/blueprint_agent_task_panel_auto_top_summary_2026-05-22.md`
  plus the relevant `archive/frontend/agent_info_panel_*` files.
- GuLiCode top Agent, organization view, top-agent profile, start plan, and
  status explanation: read `多agents通信设计.md`, then
  `tasks/multi_agent_communication_tasks.md`.
- Runtime start/status/end, organization, message batch, agent dispatch,
  join-create, and join-contribute: read `knowledge_base/dispatch_workflows.md`.
- Current architecture or component ownership:
  read `knowledge_base/core_architecture.md`.
- `GraphDefinition.agent_cycle_groups()` and cycle/loop handling:
  read `knowledge_base/ring_structure_solution.md`, then
  `knowledge_base/core_architecture.md`.
- Legacy `CodeMakerCluster`, `run_parallel`, `run_chain`, broker, and TCP worker
  path: read `knowledge_base/cluster_api.md`.
- Workspace API, changesets, archive, private checkout, conflict flow, and MCP
  workspace tools: read `knowledge_base/core_architecture.md` and
  `tasks/multi_agent_communication_tasks.md`.
- Multi CLI adapters, Codex/CodeMaker process adapters, and `CLIAdapter`:
  read `knowledge_base/multi_cli_workflow.md`.

## Working Rules

- Prefer repo-local patterns and existing tests.
- For frontend work, keep GuLiCode UI restrained, dense, and consistent with the
  current app. Avoid unrelated redesigns.
- For runtime work, keep the control-plane API as the product boundary and keep
  CLI workers as replaceable adapters.
- For ordinary agents, preserve private workspace isolation. Project mutations
  should flow through the framework workspace/MCP path, not direct writes to the
  shared project root.
- When changing skill knowledge, keep this `SKILL.md` short and move detail to
  `knowledge_base/`, `tasks/`, or `archive/`.
- When copying into `KM_docs/skills-snapshot`, mirror the current installed
  skill tree.

## Repository Link

- GitHub: https://github.com/QHXRPG-A/multi_agent_tcp
- Current common local root: `F:\src\Package\Script\Python\multi_agent_tcp`
