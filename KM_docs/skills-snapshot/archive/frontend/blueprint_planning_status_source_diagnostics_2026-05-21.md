# Blueprint Planning Status Source Diagnostics - 2026-05-21

## Summary

This pass closed the P0 planning-mode status-source mismatch.

Before this fix, the GuLiCode desktop planning chat could call
`framework_control_runtime_status` / `framework_control_top_agent_explain_status`
successfully but still answer from the planning context's no-op runtime. The
Runtime side panel was reading the active live `DesktopBlueprintRun`, so users
could see `test-agent` already `idle` while the planning chat said the blueprint
was still `created` with no active agent state.

After this fix, planning-mode status/explain/utterance MCP calls select the
active live run when one is available, and fall back to the planning context
only when no matching live run exists.

## Implemented Shape

Backend:

1. `DesktopBlueprintRun` now carries `diagnostics_dir`.
2. Each live blueprint start resets and recreates:

   ```text
   <projectDir>/.multi_agent_workspace/runs/active/<runId>/shared/logs/blueprint-diagnostics/
   ```

3. The diagnostics folder contains:
   - `snapshot.json`: latest compact status-source snapshot.
   - `events.jsonl`: chronological event stream.
4. `RunMCPRuntimeHandle` now supports optional
   `control_command_callback` and `control_call_observer`.
5. Desktop planning contexts use those callbacks to route:
   - `run.status`
   - `top_agent.explain_status`
   - `top_agent.utterances`

   to the active live `DesktopBlueprintRun` when available.
6. MCP status-class responses preserve the original response shape and add:
   - `status_source`
   - `source_run_id`
   - `planning_session_id`
7. `blueprint.planning.status` still returns `runtimeStatus` and `activeRun`,
   and now also returns `statusSource`.

Status-source rules:

```text
if planning session has a linked active live run:
  selected = active_live_run
elif a non-terminal live run exists for the same projectDir + blueprintId:
  selected = active_live_run
else:
  selected = planning_context
```

Diagnostics events:

1. `blueprint_run_started`
2. `planning_active_run_linked`
3. `planning_status_snapshot`
4. `planning_mcp_control_call`
5. `planning_status_source_mismatch`

`mismatch=true` is expected when the planning no-op runtime differs from the
active live run. It is not the bug by itself. The important field is
`statusSource.selected`; Top Agent should use `active_live_run` when a live run
exists.

## Verification

Automated verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m py_compile desktop_blueprint_service.py blueprint_mcp_runtime.py test_desktop_blueprint_service.py
python -m pytest -q test_desktop_blueprint_service.py

cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-planning-session.test.ts
```

Latest observed result:

```text
31 passed, 1 skipped, 2 warnings
1 pass, 0 fail
```

Manual GuLiCode desktop evidence:

1. Debug startup succeeded with renderer at `http://localhost:5173/` and sidecar
   at `http://127.0.0.1:8097`.
2. Live run:

   ```text
   D:\agents_work_test\.multi_agent_workspace\runs\active\run-cd9366eea7f2
   ```

3. Diagnostics:

   ```text
   shared/logs/blueprint-diagnostics/snapshot.json
   shared/logs/blueprint-diagnostics/events.jsonl
   ```

4. `snapshot.json` showed:

   ```text
   planning_context: run=created, agents={}
   active_live_run: run=running, test-agent=idle, queue=0
   selected: active_live_run
   mismatch: true
   ```

5. `events.jsonl` MCP call evidence:

   ```text
   runtime_status -> run.status
   selected: active_live_run
   source_run_id: run-cd9366eea7f2
   output run status: running
   output test-agent state: idle

   top_agent_explain_status -> top_agent.explain_status
   selected: active_live_run
   source_run_id: run-cd9366eea7f2
   explanation: "run is running; no pending runtime work is visible"
   ```

## Files Touched

Core implementation:

- `blueprint_mcp_runtime.py`
- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`

Behavioral surface:

- planning MCP status/explain/utterance calls now read the active live run when
  a live run is linked or discoverable for the same `projectDir + blueprintId`.
- run summaries now include diagnostics paths for live runs.
- no Electron IPC was added for diagnostics in this pass.

## Follow-Up Queue

1. Manually smoke side-panel/manual Start while a planning context already
   exists; the implementation falls back to the latest matching non-terminal
   live run, but this deserves a desktop smoke.
2. Consider throttling or deduplicating repeated
   `planning_status_source_mismatch` events during polling; the current version
   favors visibility over compactness.
3. Optional UI follow-up: surface the diagnostics path from `run.summary()` in
   a developer/debug affordance.
4. Keep an eye on mojibake in Windows terminal display. The framework writes
   JSON with UTF-8, but PowerShell rendering can make historical Chinese text
   look corrupted.

