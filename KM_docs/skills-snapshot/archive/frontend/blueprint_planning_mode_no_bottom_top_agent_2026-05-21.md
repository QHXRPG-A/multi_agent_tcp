# GuLiCode Desktop Blueprint Planning Mode - 2026-05-21

## Summary

This pass changed the desktop blueprint planning direction from "start a
bottom Top Agent worker" to "GuLiCode desktop/current chat session is the Top
Agent product role".

There is no separate Top Agent CLI/session/worker in the v1 desktop planning
path. The desktop app provisions a planning context only when the user selects
the virtual `blueprintPlanning` mode and sends the first planning message in a
desktop session.

## Implemented Shape

Backend:

1. `DesktopBlueprintPlanningSession` replaces the previous bottom
   `DesktopTopAgentSession` concept.
2. Planning sessions are keyed by `projectDir + blueprintId +
   desktopSessionId` and reused while alive.
3. Planning context loads the current blueprint graph and creates a
   framework-owned no-op `GraphRuntime` plus `GraphRuntimeControlPlane` only
   for organization reads, validation, status/explain scaffolding, pending
   question storage, and pending plan storage.
4. Planning context does not call `CLIWorkerBackend.create`, does not start a
   Top Agent worker, and does not expose `top_agent_start_session`,
   `top_agent_ask`, or `runtime_start`.
5. Planning MCP exposes the desktop planning control subset:
   organization/status/explain/utterances, `runtime_validate_start`,
   `top_agent_request_user_input`, and `top_agent_stage_start_plan`.
6. Planning session id remains stable for UI/session reuse, but the internal
   temporary workspace run id now has a random `-ctx-*` suffix. This avoids
   `run workspace already exists` after debug restarts leave old
   `.multi_agent_workspace/runs/active/planning-*` directories on disk.
7. The planning system prompt now names the actual prefixed MCP tools such as
   `framework_control_runtime_validate_start` and instructs the model to stop
   if those tools are not visible.

App / Electron:

1. The bottom composer agent dropdown has a virtual "blueprint planning" mode.
   Normal Build/Plan/agent choices continue to send ordinary chat.
2. `PromptInput` gates planning behavior behind `blueprintPlanning` only.
3. The first planning message ensures context, registers the dynamic
   `framework_control` MCP server, and attaches the framework system prompt to
   the current user message. The system prompt is attached every planning
   message because OpenCode `system` is per-message.
4. Dynamic MCP registration now trusts the return value of `mcp.add`. It no
   longer calls `mcp.status()` as the connection oracle, because status only
   enumerates persistent config entries and can omit runtime-injected MCP
   servers.
5. The main content area stays on the normal `MessageTimeline`; planning
   question and plan confirmation UI are composer-adjacent docks.
6. Approving a staged plan is app-mediated: the UI calls existing
   `startBlueprintRun(..., "live")`, then calls
   `markBlueprintPlanningPlanStarted` for audit/status linkage.
7. Solid store proxies are cloned before Electron IPC so approve/start no
   longer fails with `An object could not be cloned`.
8. `ensureBlueprintPlanningContext` now uses `projectDirectory`, not
   `sessionDirectory`, so planning context is created under the blueprint
   project root.
9. Electron runtime errors now include service `details.error`, which exposed
   the stale run-workspace collision during debugging.

## Verification Run In This Pass

Backend:

```powershell
pytest -q test_desktop_blueprint_service.py::test_blueprint_service_desktop_planning_context_plan_flow -q
python -m py_compile desktop_blueprint_service.py test_desktop_blueprint_service.py
```

App:

```powershell
cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-planning-session.test.ts ./src/components/prompt-input/submit.test.ts
bun run typecheck
```

Electron:

```powershell
cd GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
```

Manual/debug observations:

1. Direct `blueprint.planning.ensureContext` succeeds against
   `D:\agents_work_test`.
2. A deliberately stale `runs/active/planning-*` workspace no longer blocks
   planning context creation; the new workspace run id is
   `planning-...-ctx-...`.
3. Direct dynamic `mcp.add` against the active OpenCode sidecar returned
   `connected`.

## Important Open Issue

Superseded later on 2026-05-21 by
[`blueprint_planning_status_source_diagnostics_2026-05-21.md`](blueprint_planning_status_source_diagnostics_2026-05-21.md):
the planning-mode status-source mismatch was fixed and verified with
run-scoped diagnostics.

Highest priority next: planning-mode status can be stale or misleading because
the planning MCP is currently bound to the planning context's no-op runtime,
not necessarily to the active live blueprint run shown in the Runtime side
panel.

Observed user-visible mismatch:

1. The right Runtime panel shows the blueprint has been started.
2. The `test-agent` entry is `idle`, which means the agent has been pulled up.
3. Queue/message state in the Runtime panel shows a completed message.
4. The planning chat answered that the current blueprint state is `created`,
   no agent was pulled up, and no job is running.

Working hypothesis:

1. `framework_control_runtime_status` in planning mode reads
   `DesktopBlueprintPlanningSession.runtime`, the planning no-op runtime.
2. The Runtime panel reads the active `DesktopBlueprintRun` live runtime.
3. `DesktopBlueprintPlanningSession.active_run_id` is populated only through
   the planning approve path (`markPlanStarted`). If the user starts from the
   side panel or if a live run already exists before planning context is
   created, planning status does not point at that live run.
4. Therefore the model can faithfully call MCP and still answer from the wrong
   status source.

Required next work:

1. Trace and document the exact data sources used by the Runtime panel,
   `blueprint.planning.status`, planning MCP `runtime_status`, and planning MCP
   `runtime_explain_status`.
2. Decide the status contract for desktop planning:
   - either planning status always proxies the active live run for the same
     `projectDir + blueprintId` when one exists;
   - or planning status returns both `planningContextStatus` and
     `activeLiveRunStatus` and the system prompt requires the model to name
     which source it is using.
3. Make side-panel/manual starts and planning-approved starts update the same
   active-run link visible to planning sessions.
4. Update MCP tools/tests so planning-mode `runtime_status` and
   `runtime_explain_status` cannot silently report the no-op planning runtime
   when a live run is active.
5. Add regression coverage for: live run already active -> planning question
   "is blueprint started?" -> MCP-visible status matches Runtime panel.
