# gulicode-bp MCP Direct Start Live Close Loop

Date: 2026-06-02

## Summary

This archive records the shift from Workbench-submitted planning requests to
Codex MCP direct control for starting Blueprint runs, plus the live runtime
close-loop fixes found during self-test.

The intended operating model is:

- Users ask in the Codex chat.
- Codex creates and validates a start plan with the `gulicode-bp` MCP tools.
- Codex starts the Blueprint with `blueprint_start(..., executionMode="live")`.
- The Workbench is an observation and manual direct-run surface, not a planning
  inbox source.

## Key Changes

- Removed the Workbench planning inbox backend.
  - Removed `blueprint.planning.submit/status/cancel` request handling from
    `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`.
  - Removed `planning_requests.json` state and the
    `blueprint_take_planning_request`,
    `blueprint_complete_planning_request`, and
    `blueprint_fail_planning_request` MCP tools.
  - Kept direct-control MCP tools: `blueprint_plan_create`,
    `blueprint_plan_validate`, `blueprint_start`, `blueprint_status`,
    `blueprint_recent_events`, `blueprint_run_diff`, and `blueprint_end`.
- Made live start return promptly.
  - `DesktopBlueprintService.start_blueprint_run` now registers a
    `DesktopBlueprintRun` first, then completes `GraphRuntimeControlPlane`
    live start in the desktop async loop.
  - Added `startPending` projection so callers can distinguish registered run
    state from fully started runtime state.
  - Added starting snapshots for `listRuns/status/recentEvents` while the
    background live start is still completing.
- Fixed cancelled runs leaving a disk manifest as `running`.
  - `GraphRuntime.end_run()` now writes terminal state into
    `run_manifest.json` for `cancel`, `fail`, `complete`, and `pause`.
  - The self-test now verifies `run_manifest.status` changes from `running` to
    `cancelled` after `blueprint_end(cancel)`.
- Fixed Windows extended-path snapshot failures.
  - Workspace copy path comparisons strip `\\?\` and `\\?\UNC\` prefixes before
    relative path checks.
  - This prevents long `node_modules/.bun/...` paths from failing
    `_path_is_copy_excluded()` with `ValueError: is not in the subpath`.
- Fixed installed plugin runtime refresh.
  - `install_personal_plugin.py` now reinstalls the freshly built wheel into
    the personal plugin `.runtime/venv` even when preserving runtime state.
  - This prevents a packaged Workbench/service from serving stale Python code
    after source changes.

## Self-Test Flow

The successful direct-control smoke used:

```text
projectDir = F:\src\Package\Script\Python\multi_agent_tcp
blueprintId = default
startNodeIds = ["agent"]
executionMode = live
```

Validated graph:

```text
agent -> coder -> review -> summary
```

MCP sequence:

1. `blueprint_open(default)`
2. `blueprint_plan_create(..., startNodeIds=["agent"])`
3. `blueprint_plan_validate(...)`
4. `blueprint_start(..., executionMode="live")`
5. `blueprint_list_runs`
6. `blueprint_status`
7. `blueprint_recent_events`
8. `blueprint_run_diff`
9. `blueprint_end(action="cancel", reason="self-test complete")`

Observed results:

- `blueprint_start` returned instead of hanging.
- `listRuns` projected `startPending=false` and `status=running` once startup
  completed.
- Workbench showed the same run ID and `status: running`.
- `blueprint_end(cancel)` returned `final_status=cancelled`.
- MCP runtime state moved to `closed`.
- `run_manifest.json` was updated to `status=cancelled`.
- No broker/worker process remained after close.

Later external-start observation:

- A follow-up MCP-started run, `run-470f52a8a2cb`, was left running while the
  Workbench sync bug was investigated.
- A later `blueprint_list_runs` poll showed it had naturally reached
  `status=completed`, `finalStatus=failed`, and MCP `state=closed`.
- That terminal failed result is separate from the live-start close-loop fixes:
  the startup path returned, the run became observable, and the backend closed
  instead of leaving a live active run behind.

## Verification

Targeted Python tests:

```text
python -m pytest test_agent_runtime.py -k "manifest or end_run_final_statuses"
python -m pytest test_workspace_manager.py -k "windows_extended_path_prefix or full_scope_prunes_workspace_root"
python -m pytest test_desktop_blueprint_service.py -k "gulicode_bp_mcp or plan_create or plan_validate or blueprint_start or listRuns or active_run or close_live_backend or live_mode_starts_start_agents or live_start_returns_pending"
```

Results:

- `test_agent_runtime.py`: passed.
- `test_workspace_manager.py`: passed.
- `test_desktop_blueprint_service.py`: passed with only existing websockets
  deprecation warnings.

Frontend/package verification:

```text
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts
bun run --cwd GuLiCode/packages/app typecheck
.\package-gulicode-bp-plugin.cmd -NoSmoke
```

Packaging notes:

- The personal plugin venv wheel reinstall succeeded.
- Existing Vite chunk warnings and an existing JSX import-source warning
  remained.
- Existing pip invalid-distribution warnings in the plugin venv remained but did
  not block installation.

## Operational Notes

- A Workbench port may become stale after service restart. Use
  `start_blueprint_workbench` to get the current singleton Workbench URL rather
  than trusting an old browser tab.
- `listRuns` may include terminal history in memory. A terminal run with
  `status=cancelled` is not an active run; active/running state should be read
  from `status`, `startPending`, and MCP `state`.
- Do not restore the removed Workbench planning inbox. The intended planning
  path is Codex chat plus direct MCP tools.
- Do not delete or edit unrelated dirty skill files when packaging or testing.

## Files Touched In This Work Area

- `desktop_blueprint_service.py`
- `graph_runtime.py`
- `workspace_manager.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `plugins/gulicode-bp/scripts/install_personal_plugin.py`
- `test_agent_runtime.py`
- `test_desktop_blueprint_service.py`
- `test_workspace_manager.py`
