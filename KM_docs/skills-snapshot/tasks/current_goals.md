# Current Short-Term Goals

Last cleaned: 2026-05-22

## Current Main Line

The active project direction is:

```text
Guli productization
  -> blueprint embedded in GuLiCode desktop
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace/events
  -> CLIWorkerBackend adapters
```

Primary design source:

- [`../多agents通信设计.md`](../多agents通信设计.md)
- [`guli_desktop_ui_tasks.md`](guli_desktop_ui_tasks.md)
- [`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)
- [`../knowledge_base/gulicode_desktop.md`](../knowledge_base/gulicode_desktop.md)
- [`../knowledge_base/guli_desktop_ui.md`](../knowledge_base/guli_desktop_ui.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)

## Recently Completed Baseline

This round has already established the first usable desktop/UI baseline:

- One-click packaged startup now uses `start-gulicode-desktop.cmd --packaged`.
- Packaged output is stabilized at `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`.
- Packaged startup now waits for renderer assets, tolerates `electron-builder` partial Windows sign-tool noise, and patches the final `exe` icon with `rcedit`.
- Packaged main-window bring-up is hardened against off-screen saved window state and icon-load failures inside the Electron main process.
- Desktop icon assets have been replaced for `dev` / `beta` / `prod`.
- The new-session empty state now shows `GULI`.
- The session header blueprint entry now opens a GuLiCode-owned right-side blueprint panel.
- The blueprint panel now contains a runtime-aligned local graph workbench:
  default seed graph, persisted `BlueprintDraft`, HTML nodes plus SVG edges,
  selection, node drag, right-click canvas pan, wheel zoom, add-node dropdown,
  drag/drop node creation, port-to-port connection, context-menu deletion,
  keyboard deletion, reset/fit view, and inspector editing.
- The local graph model now includes `route_nodes`, full `AgentNode`
  configuration fields, terminal node kinds, route node kinds, and port-aware
  `GraphEdge` fields with default `out -> in` exec edges.
- Every canvas node now renders at least one connection port: Start has output,
  End has input, and Agent/Route nodes have both input and output.
- Inspector fields now include per-field `?` tip buttons describing what each
  setting is and what it is used for.
- The blueprint panel has passed the current dark, technology-oriented,
  minimal visual pass. Nodes are intentionally more distinct from the canvas
  background, and the inspector uses a dark surface with light labels,
  visible question buttons, corrected select option colors, and legible
  `nonblocking` / `非阻塞` labels.
- `toRuntimeGraphDraft(draft)` now preserves the shape needed for later
  `{ terminal_nodes, agent_nodes, route_nodes, edges }` runtime conversion
  without invoking runtime execution from the renderer.
- The blueprint common config panel now owns user-visible
  `project_workdir`, `skill_dir`, and `rule_dir`. User-machine local paths are
  no longer hard-coded in code defaults; `skill_dir` and `rule_dir` start empty
  and must be set by the user when the blueprint needs them.
- The Agent inspector now hides framework-managed execution fields:
  `cwd`, `read_scope`, `write_scope`, `artifact_scope`, `workspace_id`,
  `workspace_root`, editable `command`, and raw `skill_selection`.
- Runtime draft export still preserves backend compatibility: common
  `project_workdir` is written to AgentNode `cwd`, `command` is generated from
  `cli_kind`, selected skills are mirrored into both `skills` and
  `skill_selection`, and empty skill selection writes `{ mode: "none" }`.
- Skill and rule fields are multi-select dropdowns backed by the common
  directories. Rule directories can be empty without error.
- CLI kind and model are dropdowns. Electron IPC now lists skill/rule catalogs
  and refreshes model candidates by running `codemaker models netease-codemaker`
  or parsing `codex debug models` JSON.
- `adapter_options` remains visible only as an advanced JSON field for
  low-level CLI adapter fallback parameters.
- The latest packaged smoke output was regenerated at `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe` on 2026-05-14 after the resizable blueprint divider change.
- Full Windows installer packaging has a documented local workaround for
  electron-builder `winCodeSign` symlink extraction failures: temporary local
  config, `win.signAndEditExecutable = false`, and `afterPack` `rcedit`
  icon patching.
- The full Windows NSIS workaround was run successfully on 2026-05-14 and
  produced `dist/opencode-electron-win-x64.exe`,
  `dist/opencode-electron-win-x64.exe.blockmap`, and
  `dist/win-unpacked/GuLiCode Dev.exe`. If `d3dcompiler_47.dll` cannot be
  removed, terminate old `GuLiCode Dev.exe` processes launched from
  `dist/win-unpacked` and rerun the workaround.
- 2026-05-18 live runtime pass is complete enough for first UI smoke:
  `blueprint.start` supports `status/live`, live mode starts
  `CLIWorkerBackend` + `GraphRuntimeControlPlane` + `GraphRuntime` tick loop,
  and the desktop service owns backend/tick/WebSocket cleanup.
- Agent stream is now a unified `AgentStreamEvent` model. `HTTP/IPC` remains
  the control plane for start/status/end/agentInfo/queue/token, while WebSocket
  is the event plane for Agent status, queue updates, message parts, public
  reasoning summaries, tool calls, final message completion, and errors.
- GuLiCode blueprint canvas now has an Agent information panel opened by
  left mouse long-press with a circular progress ring, or through the Agent
  node right-click `信息面板` context menu. Hover opening is retired.
- Agent information panels support close, pin, multiple pinned panels,
  non-pinned outside-click close, stream transcript, `default/top` message
  sends, read-only static display when no live run exists, title-bar drag move,
  and bottom-right handle resize with canvas clamping.
- The Agent panel close bug was fixed by replacing the Solid store `panels`
  object with `reconcile(panels)` rather than shallow-merging filtered objects.
- The 2026-05-18 desktop debug cleanup fixed noisy code-level errors around
  `blueprint-list-models` Windows `spawn EPERM`, Solid DnD nonexistent
  droppable/draggable cleanup, stale PTY WebSocket teardown, and blueprint SVG
  render computations.
- Clean debug startup is documented after packaging instructions:
  run Electron dev with `ELECTRON_ENABLE_LOGGING=1`,
  `ELECTRON_ENABLE_STACK_DUMPING=1`, and no `DEBUG=*`.
- Test Agent panel JSON has been reduced to the v2 message-only debug shape:
  fixed `agent-panel-test.json`, payload arrays `agentReplies`,
  `userMessages`, and `frameworkMessages`, no raw `node`, `panel`, `runtime`,
  or `streamEvents` objects.
- Agent information panel status events now project into structured UI instead
  of raw JSON. Visible transcript events hide `status`, `message.started`,
  `queue.updated`, `tool.started`, `tool.completed`, stderr deltas, reasoning
  deltas, and Codex internal log lines; user-facing `part.delta` /
  `message.completed` content is grouped as `Agent 回复`.
- Agent information panels can be dragged outside the visible canvas after
  opening, body content is selectable/copyable, and wheel scrolling is handled
  inside the panel body.
- Latest Windows package after the panel cleanup was rebuilt at
  `GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe` on
  2026-05-18.
- The desktop blueprint live runtime now starts through the framework-managed
  private Agent context: `GraphRuntime(enforce_private_agent_context=True)`,
  private checkout cwd, private `CODEX_HOME`, `framework-agent-runtime`,
  `AGENTS.md`, Workspace API prompt/context, and authorized skill/rule
  materialization.
- Blueprint start is now guarded by common config validation in both renderer
  and desktop service. `project_workdir` is always required and absolute;
  `skill_dir` is required when skills are used; `rule_dir` is required when
  rule files are selected; any non-empty optional path must be absolute.
- Rule catalog selections now store filenames relative to configured `rule_dir`
  instead of user-machine absolute paths. The desktop service resolves them
  from common config during start.
- Backend workspace merge regression is fixed: non-overlapping same-file
  checkout submits are accepted even when Dulwich is unavailable or reports a
  false conflict, and the combined
  `test_desktop_blueprint_service.py test_workspace_manager.py` run passes.

## Immediate Handoff For The Next Agent

Start from these source files:

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/context/layout.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `desktop_blueprint_service.py`
- `agent_launch_context.py`
- `graph_runtime.py`
- `cluster.py`
- `test_desktop_blueprint_service.py`

Before changing behavior, run:

```powershell
cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build
```

If touching Electron catalog/model IPC, runtime IPC, or packaged desktop
identity, also run:

```powershell
cd GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run build
```

For clean debug startup with visible Electron errors:

```powershell
cd GuLiCode\packages\desktop-electron
$env:ELECTRON_ENABLE_LOGGING = '1'
$env:ELECTRON_ENABLE_STACK_DUMPING = '1'
Remove-Item Env:\DEBUG -ErrorAction SilentlyContinue
bun run dev
```

Do not use `DEBUG=*` by default; it floods the terminal with Babel/Vite
internal traversal logs.

## Active Priorities

2026-05-22 highest priority: Test Agents communication validation.

The next work should treat Test Agent communication as the first priority,
ahead of new Top Agent product planning or broader UI polish. The immediate
goal is to keep blueprint fan-out/fan-in behavior observable and aligned with
the framework contract.

Priority checklist:

1. Run small blueprints with one upstream Test Agent and multiple downstream
   Test Agents; confirm every required downstream target receives its own
   framework-delivered message and current batch.
2. Compare per-agent information panel JSON snapshots under
   `agent-info-panel-tests`; there should be one file per Test Agent node id,
   and same-name nodes intentionally overwrite the same file.
3. Inspect ordinary Agent MCP logs for misuse of upstream batch ids,
   `agent_dispatch` on leaf nodes, and `join_contribute` with `out-*` ids.
   These should now be prevented first by framework rules/skill and corrected
   second by MCP error guidance.
4. Verify leaf Test Agents publish receipts/results through shared reports
   (`workspace_publish` / `workspace_publish_file`) instead of dispatching or
   joining when `required_outgoing_targets` is empty.
5. Keep any new fixes scoped to communication contract convergence:
   current batch ownership, downstream target scope, shared report receipts,
   and join id boundaries.

Detailed archive:

- [`../archive/test_agent_communication_priority_2026-05-22.md`](../archive/test_agent_communication_priority_2026-05-22.md)

2026-05-21 GuLiCode desktop bottom Top Agent capability planning:

New task, concrete strategy TBD:

1. Define how GuLiCode desktop should expose Top Agent as a first-class
   governance/control capability at the desktop/runtime layer, not as an
   unrestricted root executor.
2. Shape the product loop around:
   user demand -> Top Agent console -> organization/status context ->
   validated `TopAgentStartPlan` -> optional plan confirmation ->
   `run.start` -> runtime status/explain/end.
3. Keep `GraphRuntimeControlPlane` / `GraphRuntime` authoritative for
   scheduling, workspace writes, agent dispatch, archive, conflict handling,
   and final run status.
4. Decide the concrete strategy later: UI entry placement, lazy vs persistent
   Top Agent session lifecycle, permission gates, plan confirmation UX,
   manifest/audit records, and whether any event-driven follow-up is allowed.
5. Avoid always-on automatic intervention until the policy and user-visible
   controls are explicit.

2026-05-20 Agent information panel stream UI update:

Closed in this pass:

1. Agent information panels now default to tall mode (`420 x 620`) and no
   longer expose the old width/height preset selector.
2. The top status strip defaults to the four compact fields: status, queue,
   messages, and busy count.
3. "运行状态" and "JSON 位置" are available only from the top status detail
   expander, not from the chat body or composer.
4. Panel-sent user messages are recorded and displayed immediately for every
   Agent. Runtime lifecycle sync remains event-driven; Test Agent JSON writes
   are still limited to Test Agent nodes.
5. Transcript projection now has explicit tones for user messages, Agent
   replies, reasoning summaries, tool calls, queue errors, and generic visible
   events.
6. Reasoning and tool entries are collapsible. Their open state is controlled
   by `agentPanelEventOpen`, keyed by display event id, so stream/status ticks
   do not collapse content the user opened.
7. Consecutive tool calls are grouped by default when no visible user/Agent
   reply, reasoning, error, or other content interrupts them. Hidden status
   ticks do not break the group. The grouped row renders as
   `工具调用组 · N 个工具` and expands to the individual tool details.

Detailed archive:

- [`../archive/agent_info_panel_stream_ui_2026-05-20.md`](../archive/agent_info_panel_stream_ui_2026-05-20.md)

2026-05-20 Blueprint project workdir + Agent surface update:

Closed in this pass:

1. Blueprint project workdir now drives the real session/workspace root:
   entering the blueprint panel prompts the user to confirm/select the project
   directory, and a changed directory relocates the current blueprint document
   to `<target>/.multi_agent_workspace/blueprints/default.json` before opening
   the target session.
2. Runtime/start/stop loading disables the blueprint common config entry; the
   common-config `project_workdir` field is read-only and can only be changed
   through the folder picker plus backend relocation flow.
3. Ordinary Agents now read `project_context` / `project_code_root` and the
   current run `shared_workspace` directly from injected read-only filesystem
   paths.
4. Ordinary/control MCP no longer exposes `workspace_read`, `workspace_list`,
   `workspace_list_archives`, or `workspace_extract_archive`.
5. `workspace_api.py` and `WorkspaceRPCServer` no longer expose Agent-facing
   `read`, `list`, `list-archives`, or `extract-archive`; internal manager
   read/archive methods remain available for framework status, reports,
   archive, and tests.
6. Ordinary Agent prompt-facing context no longer includes `workspace_api`,
   `submit_command`, or CLI command recipes. CLI/RPC stays in full internal
   `execution_context` for framework internals, tests, and debugging.
7. Codex launch safety now protects `project_context`, `project_code_root`, and
   the run `shared_workspace.root` from `--add-dir` writable escapes, and still
   rejects `danger-full-access`.

Current ordinary Agent-facing model:

```text
read project/shared directly
edit code only in private checkout
submit code through MCP
publish reports/artifacts through MCP
communicate through agent_dispatch / join_contribute
```

Detailed archive:

- [`../archive/blueprint_project_workdir_agent_surface_2026-05-20.md`](../archive/blueprint_project_workdir_agent_surface_2026-05-20.md)

Immediate next checks:

1. Manual GuLiCode desktop smoke with a user-selected project workdir and the
   relocation conflict branches.
2. Full MCP live run under a normal project directory such as
   `D:\agents_work_test`, not `C:\`.
3. Agent panel follow-up-send smoke after the status/idle and message-context
   changes: confirm late replies are still streamed and recorded.

2026-05-19 MCP full-control acceptance update:

MCP is accepted as the full run-scoped tool protocol for live blueprint Agents.
The layer now covers the public `GraphRuntimeControlPlane` control surface with
separate ordinary-Agent and top-agent/control tool boundaries. Ordinary Agents
receive only scoped execution tools; Top Agent receives orchestration,
observation, lifecycle, message, join, utterance, and status tools.

The original ordinary-agent adoption blocker was Codex CLI non-interactive MCP
approval: JSONL showed `mcp_tool_call` followed by
`user cancelled MCP tool call` before requests reached the framework MCP
server. Private `CODEX_HOME/config.toml` now writes `enabled_tools` and
per-tool `approval_mode = "approve"` for the run-scoped framework MCP server.

Closed in this pass:

1. Runtime dependencies are declared and install through
   `python -m pip install -e .`: `mcp`, `uvicorn`, `starlette`, and `httpx`.
2. The run-scoped ordinary/control MCP servers start through the full live
   framework path and expose the intended ordinary/control public tool sets.
3. MCP tool calls are audited as `framework_mcp_tool_call` with safe argument
   summaries, while Workspace RPC still audits `workspace_api_call`.
4. Private `CODEX_HOME` MCP config is materialized with token env vars, and
   prompt-facing context exposes direct-read project/shared roots while still
   excluding bearer tokens, RPC tokens, raw Codex home paths, and real
   skill-space source paths.
5. Deterministic live MCP client tests cover checkout/status/diff/submit,
   publish/publish_file, direct shared report reads, `agent_dispatch`, runtime
   control caveats, and message journal flow.
6. Skill/rule injection remains part of the private Agent context:
   `framework-agent-runtime`, selected business skill/rule, and checkout/base
   `AGENTS.md` are materialized.
7. Real Codex MCP smoke now passes through the full framework backend live
   flow; no fallback `python -m multi_agent_tcp.workspace_api` shell command is
   used in that acceptance path.
8. Control MCP parity is implemented for organization/top-agent context,
   run validate/start/status/end, message batch/stage, control-side
   `agent_dispatch`, join create/contribute, top-agent utterances, and
   status inspection. Workspace read/list/archive tools are intentionally not
   exposed to Agents.
9. `runtime_end` now prefers the `DesktopBlueprintService` live close callback,
   which tears down the backend path and closes MCP tokens.
10. Real-smoke transport hardening is complete: live stderr stream noise is
    capped and Codex stdout/stderr are compacted over TCP while full
    diagnostics remain available on disk.

Accepted real-Codex evidence:

1. `MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP=1 pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv`
   passed on 2026-05-19: `1 passed, 2 warnings in 135.84s`.
2. Codex JSONL and runtime `agent_stream_events` showed real MCP tool invocation
   rather than fallback `python -m multi_agent_tcp.workspace_api` CLI commands.
3. `run.shared/manifest.json` contained `framework_mcp_tool_call` entries for
   `workspace_checkout`, `workspace_status`, `workspace_diff`,
   `workspace_submit`, `workspace_publish`, `workspace_publish_file`,
   and `agent_dispatch`, plus corresponding `workspace_api_call` entries where
   Workspace RPC is used. The downstream reviewer reads the shared report file
   directly from `shared_workspace.reports`.
4. The project file remained at base content before submit and contained the
   test marker exactly once after accepted `workspace_submit`.
5. Final/report text proved framework skill, selected business skill, and
   selected business rule were injected.
6. Planner/reviewer flow proved cross-Agent information still moves through
   `agent_dispatch`, the message journal, queues/ticks, and shared references;
   natural language replies remain private utterances unless explicitly
   dispatched.

Remaining queue after MCP full-control acceptance:

1. Reproduce the original Agent timeout/panel-message scenario with MCP
   enabled; verify active message context refresh, Codex JSONL completion, and
   WebSocket stream continuity after follow-up sends.
2. Keep or extend the real direct-write boundary smoke in the MCP-enabled
   private context, especially project/shared write denial versus private
   checkout write allowance.
3. Add negative HTTP/MCP coverage for missing bearer token and
   `Mcp-Session-Id` reuse across ordinary/control endpoints.
4. Add UI-facing top-agent/operator surfaces for MCP control status and
   utterance audit without exposing those tools to ordinary Agents.

2026-05-19 priority update:

The desktop blueprint `live` private-context startup blocker and the
`DulwichWorkspaceManager` non-overlapping same-file merge regression are closed
at code and unit-test level. The remaining first task is a manual GuLiCode
desktop smoke pass using user-provided common config paths.

Secondary 2026-05-18 Codex/UI priority context:

Codex-first update: for this project phase, do not spend new work on
CodeMaker streaming. Prioritize `cli_kind=codex` live runs, `CodexAdapter`
JSONL streaming, WebSocket stability, and Agent information panel transcript
quality. CodeMaker stays compatibility/fallback unless the user explicitly
re-opens that track.

1. Manually smoke the live blueprint path in GuLiCode desktop: start live run,
   tick loop, runtime panel updates, Agent panel long-press progress,
   right-click `信息面板`, move/resize, close/pin, WebSocket transcript, and
   `default/top` queue sends.
2. Decide durable blueprint persistence ownership: local draft, project JSON,
   workspace records, and migration from `Persist.workspace(projectDir,
   "blueprint-draft.v1")`.
3. Continue keeping renderer logic as runtime/control-plane projection only;
   do not move GraphRuntime scheduling semantics into the UI.
4. Stabilize Agent output streaming on the Codex path before investigating any
   CodeMaker adapter streaming work.
5. Harden Windows packaging into a repeatable helper and keep clean debug
   startup as the default troubleshooting path.

Superseded 2026-05-14 priority list kept for historical context:

1. Bind the blueprint draft UI to `GraphRuntimeControlPlane` and `GraphRuntime` without moving scheduler semantics into the renderer.
2. Decide durable blueprint persistence ownership: local draft, project JSON, workspace records, and migration from `Persist.workspace(projectDir, "blueprint-draft.v1")`.
3. Extend the existing Electron/preload catalog bridge into the Python/runtime bridge needed for graph load/save and runtime start/status/end.
4. Project runtime/control-plane status into GuLiCode UI: runs, agents, outgoing batches, joins, workspace changes, artifacts, reports, and top-agent explanations.
5. Frontend smoke the current blueprint interaction and config pass: common config panel, skill/rule multi-selects, CLI/model dropdown refresh, right-click canvas pan, right-click node menu, double-click inspector, add-node click/drop, port drag connection, grid snapping, inspector collapse, and keyboard delete.
6. Frontend visual-smoke the current blueprint style pass: dark inspector
   surface, light labels, tip buttons, select menu colors, `非阻塞`
   visibility, and node/background contrast.
7. Harden Windows packaging: turn the successful NSIS/rcedit workaround into
   a repeatable script or doc-backed helper, verify installer plus unpacked
   exe icons, avoid temporary config drift, and kill only old packaged
   `GuLiCode Dev.exe` instances when the output directory is locked.
8. Continue brand unification across desktop window title, taskbar identity, packaged icons, empty states, and any remaining user-visible `OpenCode` wording.
9. Expose top-agent/operator audit surfaces only in top-level UI views, not as ordinary-Agent message context.
10. Keep workspace/archive behavior aligned with framework-owned changeset, conflict, report, artifact, and reference records.
11. Keep Tauri secondary on this machine; Electron remains the default bring-up and verification path.

## 2026-05-14 Testing Focus

1. Desktop packaged smoke:
   - Run `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged`.
   - Verify the produced app launches from `dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`.
   - Verify Electron main log reaches `main window created`.

2. Icon and branding smoke:
   - Verify the packaged `exe` carries the GuLiCode icon.
   - Verify `dist/win-unpacked/GuLiCode Dev.exe` carries the GuLiCode icon
     after the `rcedit` patch, not the stale Electron icon.
   - Verify the generated NSIS installer is rebuilt after the icon patch.
   - Verify the new-session center surface still says `GULI`.
   - Verify the session header blueprint button renders and toggles the blueprint panel.

3. Blueprint embedding smoke:
   - Click the blueprint entry in the session header.
   - Verify the right-side blueprint panel opens with the seed graph
     `start -> planner -> coder -> review -> summary -> end`.
   - Drag the session/blueprint divider and verify both panes resize like the review side panel.
   - Zoom with the mouse wheel.
   - Pan the canvas with right-click drag; left-click drag on blank canvas should not pan.
   - Left-click a node to select it without opening the inspector.
   - Double-click a node, or use the right-click node menu `Edit`, to open the inspector.
   - Use the `Add node` dropdown to create Agent, Route sequence, Route parallel,
     Route parallel_reduce, Start, and End nodes.
   - Drag an add-node menu item onto the canvas and verify the dropped position
     snaps to the 24px grid.
   - Drag from an output port to an input port and verify a port-aware `exec`
     edge appears.
   - Delete nodes and edges through right-click menu / inspector action /
     `Backspace` / `Delete`, and verify connected edges are removed with their node.
   - Verify the inspector collapses when no inspected target remains.
   - Edit Agent, Route, Terminal, and Edge inspector fields; JSON fields should
     show an invalid state while preserving the previous parsed value.
   - Verify the top-left common config panel controls project workdir, skill
     dir, and rule dir.
   - Verify the Agent inspector does not show editable command, cwd,
     workspace id/root, read/write/artifact scope, or raw skill_selection
     fields.
   - Verify skill and rule multi-select dropdowns reflect the selected
     directories and preserve selected values across save/reopen.
   - Switch CLI kind between `codemaker` and `codex`; verify the model dropdown
     enters loading state, keeps the current value on failure, and refreshes
     choices when the CLI command succeeds.
   - Click each inspector `?` tip button class in the current section and
     verify the popover explains both what the field is and what it is used for.
   - Verify inspector labels, the header text, and question buttons remain
     light-colored on the dark inspector surface.
   - Verify select controls and native option popups remain readable in the
     dark theme, especially the `nonblocking` / `非阻塞` option.
   - Verify node fills and borders remain visually separated from the canvas
     background while keeping the dark/technology/minimal direction.
   - Close and reopen the panel, then refresh and verify the local draft
     persists.
   - Close the blueprint panel and verify the previous session/review/file-tree layout remains usable.

4. Runtime/UI contract smoke:
   - Keep the rule that renderer surfaces consume runtime/control-plane state instead of rebuilding graph scheduling locally.
   - Keep durable Agent outputs flowing through framework APIs: `agent.dispatch`, Workspace API, `join.contribute`, and later structured task APIs.

## Deferred / Secondary Tracks

### CLI backend adapters

Continue maintaining Codex/CodeMaker adapters and `CLIWorkerBackend`, but do not let adapter mechanics drive product architecture.

See [`multi_cli_adapter_tasks.md`](multi_cli_adapter_tasks.md).

### Legacy Ryven/editor line

The old Ryven/editor UI line was removed from the active skill snapshot on 2026-05-13. Recover it from git history or old archives only if the user explicitly asks to restart that track.

## Validation Snapshot

Most recent desktop productization smoke observed during this round:

```text
F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged
-> builds packaged desktop app
-> patches final exe icon
-> launches GuLiCode Dev from dist/packaged-launch/current/win-unpacked

C:\Users\qiuhaoxuan\AppData\Roaming\ai.opencode.desktop.dev\logs\main.log
-> creating main window
-> main window created

Additional 2026-05-14 checks:

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
-> bun run build passes after blueprint panel and resizable divider work
-> bun run typecheck was blocked at that time by existing src/custom-elements.d.ts content (`../../ui/src/custom-elements.d.ts`); see 2026-05-18 checks for current passing state
-> bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts passes for the blueprint draft model and inspector-source boundary, including route_nodes, port-aware edges, config export, generated command, skill_selection compatibility, hidden framework-managed controls, delete cascade, runtime conversion, and grid snapping

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron\dist\packaged-launch\current\win-unpacked\GuLiCode Dev.exe
-> regenerated after the blueprint divider change

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
-> bun test ./src/main/blueprint-catalog.test.ts passes for codemaker/codex model parsing and skill/rule directory scanning
-> bun run build passes
-> default bun run package:win can still fail in a normal Windows session on winCodeSign symlink extraction
-> successful local installer workaround: temporary electron-builder.local.config.ts, win.signAndEditExecutable=false, afterPack rcedit icon patch, CSC_IDENTITY_AUTO_DISCOVERY=false, ELECTRON_BUILDER_RCEDIT_PATH=<cached winCodeSign rcedit dir>, bunx electron-builder --win --config electron-builder.local.config.ts
-> if old dist/win-unpacked/GuLiCode Dev.exe processes are still running, builder can fail removing d3dcompiler_47.dll; close/kill those old output-dir instances and rerun
-> produced dist/opencode-electron-win-x64.exe, dist/opencode-electron-win-x64.exe.blockmap, and dist/win-unpacked/GuLiCode Dev.exe with the corrected icon
-> 2026-05-14 successful artifact timestamps: installer 18:13:35, blockmap 18:13:37, win-unpacked exe 18:13:03

Additional 2026-05-18 live runtime / Agent panel checks:

F:\src\Package\Script\Python\multi_agent_tcp
-> python -m py_compile desktop_blueprint_service.py graph_runtime.py client.py broker.py adapters.py codex_bridge.py cluster.py __main__.py test_desktop_blueprint_service.py passes
-> pytest -q test_desktop_blueprint_service.py test_multi_agent_tcp_cli.py passes with local multi-agent-tcp CLI shim
-> focused GraphRuntime queue/worker-failure tests pass

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
-> bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts passes
-> bun run typecheck passes
-> bun run build passes

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
-> bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts passes
-> bun run typecheck passes
-> bun run build passes
-> packaging workaround produced dist/opencode-electron-win-x64.exe, dist/opencode-electron-win-x64.exe.blockmap, and dist/win-unpacked/GuLiCode Dev.exe

Additional 2026-05-18 Agent panel interaction / debug checks:

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
-> bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts passes
-> bun test --preload ./happydom.ts ./src/i18n/parity.test.ts passes
-> bun run typecheck passes
-> bun run build passes

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron\debug-logs\dev-20260518-151513.log
-> server ready
-> renderer dev server http://localhost:5173/
-> sidecar http://127.0.0.1:6168
-> no new Uncaught / EPERM / Cannot remove / agentHoverTimer errors observed
```
