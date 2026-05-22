# Blueprint Runtime Completion, Demux, And Workspace Panels - 2026-05-22

## Summary

This session closed the main blueprint runtime loop around concurrent worker
replies, runtime workspace visibility, agent tool/status UI, and agent task
completion semantics.

The largest framework fix was in `AgentTCPClient`: concurrent `run_single`
waiters now share a demuxed inbox instead of racing on a single receive queue.
The runtime can now safely wait for multiple workers whose final replies arrive
out of order.

The runtime workspace status path was also repaired so live runs project real
files from the current run workspace instead of showing empty arrays. The
desktop runtime panel now exposes workspace changes, artifacts, and reports as
interactive panels with Explorer actions.

Finally, AgentNode completion is now explicit. Agents can report task status
through a new ordinary MCP tool, the framework prompts idle agents to summarize
their own task after the configured idle threshold, start-node validation covers
source components, and the runtime emits a top-agent summary-ready event after
all blueprint agents reach terminal task states.

## Implemented Shape

Agent reply demux:

1. `client.py` added a private inbox protected by a condition variable.
2. The receive pump enqueues ordinary broker messages into that inbox and
   notifies all waiters.
3. `wait_for_message(expect_from=...)` scans the inbox and only consumes
   messages whose sender matches the waiter.
4. Nonmatching final replies and stream events stay in the inbox for the
   matching waiter.
5. `agent.stream` remains non-final: matching stream events call their callback
   and continue waiting for the final worker reply.
6. `incoming()` now consumes through the same inbox so it does not compete with
   `wait_for_message()` through a separate queue.
7. Broker `error` messages and connection-close behavior keep the previous
   semantics.

Runtime workspace hydration:

1. `GraphRuntime._workspace_state_snapshot()` now hydrates from the live run
   workspace, preferring `archive_run` and falling back to
   `private_context_run`.
2. Reports and artifacts are projected from disk under `shared/reports` and
   `shared/artifacts`.
3. Manifest `write` entries supplement owner/version/bytes/timestamps but do
   not replace disk enumeration.
4. Accepted changesets are projected with changeset id, path, absolute path,
   changed files, agent id, and status.
5. Workspace status includes `workspace_root`, `shared_root`, and directory
   fields for changesets, artifacts, and reports while preserving the existing
   `changesets`, `conflicts`, `artifacts`, `reports`, and `jobs` structure.
6. `DesktopBlueprintService` creates live `GraphRuntime` instances with the
   same `archive_manager` and `archive_run` used by the workspace run.

Desktop workspace and event UI:

1. The runtime workspace metrics for changes, artifacts, and reports became
   clickable `RuntimeWorkspaceMetric` controls.
2. Left click opens a floating `WorkspaceContentPanel` on the blueprint canvas.
3. The panel shows concrete item cards with file name and absolute path.
4. Right click on a category opens the corresponding directory in Explorer.
5. Right click on an item reveals that file or changeset path in Explorer.
6. The platform interface gained `revealPathInFileManager(path)`, implemented
   through Electron preload and `shell.showItemInFolder(path)`.
7. The runtime event panel gained a height slider and compact event rows so
   long event streams are easier to inspect in the sidebar.

Agent info panel tool categorization:

1. Tool call groups now derive a visible category from stream/tool metadata.
2. MCP tools, command/shell execution, and Codex/internal tool activity use
   distinct category styling.
3. The collapsed group status area shows the category label next to the
   success/failure state so failures can be traced to the correct tool class.

Agent task status and completion:

1. Ordinary MCP now exposes `agent_task_status`.
2. Supported statuses are `working`, `completed`, `blocked`, `needs_input`,
   and `failed`.
3. Reports can include summary, message id, batch id, reports, artifacts,
   changesets, next actions, and metadata.
4. Ordinary tokens can only report status for their bound AgentNode.
5. If there is an active message context, message and batch ids must match.
6. New message flow to an AgentNode resets the current task status to
   `working`.
7. Each `AgentInstance` tracks `has_received_flow`, `idle_since`,
   `task_status`, summary fields, and summary prompt timestamps.
8. Entering idle starts the idle timer. Entering queued, dispatching, running,
   waiting, or reply-processing states clears it.
9. After a flowed-to agent has been idle for 30 seconds and has not reported a
   terminal task status, the framework queues one `framework_summary_request`.
10. The prompt asks the agent to summarize its own current task, not the ring
    or the whole blueprint.
11. Ring agents use the same completion state machine, with only one extra gate:
    when their circulation-count dict is nonempty, all values must be zero
    before the 30 second idle prompt can fire.
12. `GraphRuntime` emits `AgentTaskStatusReported` and stream
    `agent.task_status` for reported task status.
13. When all expected AgentNodes have received flow and reached terminal task
    status, with no visible pending runtime work or conflicts, the runtime
    emits `RunReadyForTopAgentSummary` and stream
    `run.ready_for_top_agent_summary`.
14. `status_snapshot()` exposes agent task fields plus
    `run.ready_for_top_agent_summary` and summary generation ids.

Start coverage validation:

1. `GraphDefinition.agent_flow_connections()` projects Agent-to-Agent
   non-data edges.
2. `required_start_groups()` compresses the Agent execution graph into SCCs and
   returns source SCC groups.
3. Each source SCC must have exactly one selected start node.
4. Isolated AgentNodes become their own required start group.
5. Source rings allow any one member to be selected.
6. `runtime_validate_start` and top-agent start planning now expose
   `required_start_groups` and return missing, duplicate, and invalid start
   errors.
7. The top-agent rules and skill text now tell the planner to use the source
   SCC algorithm.

Top-agent and rule guidance:

1. Ordinary agent launch rules instruct agents to call `agent_task_status`
   before a final CLI reply and when receiving `framework_summary_request`.
2. The top-agent planning rules emphasize selecting exactly one start node from
   each required source group.
3. Blueprint completion keeps the graph alive for follow-up tasks; a later
   message can move a completed agent back to working.

Debug conclusions captured during the session:

1. The previous `waiting_for_reply` hang was caused by concurrent waiter queue
   consumption, not by worker process failure.
2. The observed MCP/command failure with
   `CreateProcessWithLogonW failed: 1326` points to a Windows credential or
   logon helper problem in command execution, not to blueprint message routing.
3. Agents have private workspaces, but `workspace_submit` can still conflict
   when multiple accepted changesets target the same shared files or regions.
4. Replies intentionally do not flow upstream against blueprint edge direction;
   completion is reported through task status and top-agent summary readiness,
   not reverse message edges.

## Verification

Python syntax check:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m py_compile graph_runtime.py graph_control.py blueprint_mcp_runtime.py agent_launch_context.py desktop_blueprint_service.py test_agent_runtime.py test_desktop_blueprint_service.py
```

Observed result: passed.

Runtime tests excluding real Codex worker smoke:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
pytest -q test_agent_runtime.py -k "not real_codex"
```

Observed result: 90 passed, 3 deselected.

Desktop blueprint service tests:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py
```

Observed result: 34 passed, 1 skipped, 2 warnings.

App runtime panel and i18n tests:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
```

Observed result: 13 tests passed.

App typecheck:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run typecheck
```

Observed result: passed.

Diff whitespace check:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
git diff --check
```

Observed result: no whitespace errors; Git only reported CRLF conversion
warnings.

Known verification note:

```powershell
pytest -q test_agent_runtime.py test_desktop_blueprint_service.py
```

This combined run timed out after five minutes and pytest hit a Windows
terminal flush `OSError: [Errno 22] Invalid argument`. The narrower non-real
runtime suite and the full desktop service suite were then run separately and
passed as listed above.

Local app dev server:

```text
URL:  http://127.0.0.1:5173/
Log:  F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\gulicode-app-runtime-completion.log
Err:  F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\gulicode-app-runtime-completion.err.log
```

## Main Files Touched

Python framework/runtime:

- `client.py`
- `graph_runtime.py`
- `graph_control.py`
- `blueprint_mcp_runtime.py`
- `agent_launch_context.py`
- `desktop_blueprint_service.py`
- `test_agent_runtime.py`
- `test_desktop_blueprint_service.py`
- `docs/blueprints/complex_test_blueprint.json`

GuLiCode app:

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

Desktop Electron:

- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`

## Follow-Up Queue

1. Run a manual desktop smoke with a fan-out blueprint: start all required
   source groups, verify each downstream agent reports task status, and confirm
   the top-agent summary-ready event appears only after all agents complete.
2. Exercise a ring blueprint manually: verify circulation counts reach zero
   before idle summary prompts fire.
3. Re-test the command execution path that produced
   `CreateProcessWithLogonW failed: 1326` with known-good Windows credentials
   or without the alternate-logon path.
4. Decide whether the runtime event panel height preference should persist per
   session or remain local UI state.
