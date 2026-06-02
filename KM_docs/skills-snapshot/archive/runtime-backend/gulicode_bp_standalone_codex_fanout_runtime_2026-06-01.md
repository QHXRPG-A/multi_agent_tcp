# GuLiCode BP Standalone Runtime and Codex Fan-out Smoke - 2026-06-01

## Summary

This pass continued the `gulicode-bp` standalone plugin productization work and
used a fan-out Blueprint run to expose runtime scheduling blockers.

The installed plugin path now uses a plugin-owned runtime venv, the Codex cache
`.mcp.json` is synchronized to that private Python, and standalone smoke checks
load `multi_agent_tcp` from plugin `site-packages` with repository fallback
disabled. The live fan-out smoke was switched from Codex to Codex after the
local Codex model `gpt-5.4` proved unavailable.

The main runtime fix from the fan-out smoke is reminder scheduling:
`framework_outgoing_targets_reminder` is now an actual queued agent message, but
it is only inserted when the source agent has already received flow and has no
pending queued message. This avoids reminder messages racing ahead of the real
task and creating duplicate outgoing batches.

## Implemented

Standalone/plugin install:

1. Reinstalled `gulicode-bp` 0.1.3 with a plugin-owned runtime wheel installed
   into `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\venv`.
2. Synced Codex cache plugin `.mcp.json` files for both cached 0.1.2 and 0.1.3
   to point at the installed plugin private Python.
3. Hardened `plugins/gulicode-bp/scripts/install_personal_plugin.py`:
   - force install no longer tries to delete `.runtime`, which can be locked by
     a running MCP process;
   - broken pip inside the runtime venv is repaired with `ensurepip`;
   - runtime wheel install uses `--ignore-installed --no-deps` so same-version
     local wheels still overlay updated source.

Control plane:

1. Added `_run_control_coro(...)` in `graph_control.py`.
2. Replaced direct `asyncio.run(...)` calls in synchronous
   `GraphRuntimeControlPlane.handle_request(...)` command paths.
3. This fixes MCP/FastMCP calls such as `blueprint_start` failing with
   `asyncio.run() cannot be called from a running event loop`.

GraphRuntime reminders:

1. `AgentOutgoingTargetsReminder` now queues a real top-priority
   `framework_outgoing_targets_reminder` message with the active
   `outgoing_batch_id`, `required_outgoing_targets`, and `remaining_targets`.
2. Outgoing-target and script-call reminders are suppressed when:
   - the agent has not yet received any flow message;
   - the agent already has queued messages waiting.
3. These guards prevent reminder messages from being dispatched before the
   original task message, and prevent a worker from creating duplicate
   downstream batches after it already handled a reminder.

Fan-out smoke blueprint:

1. Added/used `.multi_agent_workspace/blueprints/fanout-worker-smoke.json`.
2. Graph shape:
   - `planner` fans out to `runtime_fix`, `install_smoke`, `review_probe`;
   - all three workers flow to `summary`.
3. Switched all nodes to Codex:
   - `cli_kind: codex`
   - `command: codex`
   - `model: gpt-5.4`

## Files Changed

Runtime/backend:

1. `graph_control.py`
2. `graph_runtime.py`
3. `test_graph_control.py`
4. `test_agent_runtime.py`

Plugin installer:

1. `plugins/gulicode-bp/scripts/install_personal_plugin.py`

Blueprint smoke artifact:

1. `.multi_agent_workspace/blueprints/fanout-worker-smoke.json`

## Verification

Core Python checks:

```powershell
python -m py_compile graph_runtime.py graph_control.py desktop_blueprint_service.py
# pass

pytest -q test_agent_runtime.py::test_graph_runtime_reminds_idle_source_about_remaining_outgoing_targets test_agent_runtime.py::test_graph_runtime_waits_for_existing_agent_message_before_outgoing_reminder test_agent_runtime.py::test_graph_runtime_does_not_remind_agent_before_first_flow_message test_agent_runtime.py::test_graph_runtime_reminds_idle_source_about_required_script_calls test_graph_control.py
# 18 passed
```

Plugin install:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force --skip-web-build
# pass
```

Installed runtime smoke:

```text
GULICODE_BP_DISABLE_REPO_FALLBACK=1
PYTHONPATH=
runtimePackage = C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\venv\Lib\site-packages\multi_agent_tcp\__init__.py
beforeFlowReminderCount = 0
afterFlowReminderCount = 1
```

Fan-out status smoke:

1. Started `fanout-worker-smoke` through `DesktopBlueprintService` from the
   installed plugin runtime.
2. Manually dispatched planner to all three workers.
3. Verified `plannerRemaining` became `[]`.
4. Verified `summaryQueueSize` became `3`.

Codex live smoke:

1. Codex run was abandoned because local `codex models
   codex` listed `kimi-k2.6` but not `kimi-k2.5`.
2. A Codex live run (`run-f9f6b07cd8a4`) proved planner could call
   `agent_dispatch` to all three workers.
3. That run exposed duplicate reminder/batch behavior when reminders raced
   ahead of original messages.
4. After the reminder guards, a later Codex live run (`run-30928feeb2bd`)
   showed:
   - planner batch `remaining` became empty;
   - planner reminder count stayed `0` while its original task was running;
   - workers were dispatched through Codex CLI;
   - summary produced an interim report.

## Operational Notes

The Codex desktop side browser can keep a stale workbench URL after the service
is restarted. If `127.0.0.1:<old-port>` shows `ERR_CONNECTION_REFUSED`, check
the currently listening `start_workbench.py` process and open its ready-file
URL. In this pass, `9817` was stale after restart; later live workbench URLs
used ports such as `3580`.

Killing the currently loaded `gulicode_bp_mcp.py` process can close the MCP
transport in the active Codex thread. The installed plugin cache is corrected,
but the current thread may not auto-reconnect the MCP tool until a fresh plugin
process/session is started.

## Known Boundaries

The installed MCP path is now the validated standalone path. The repo-local
`plugins/gulicode-bp/scripts/start_workbench.py --repo-root ...` debug script
was used for observable live runs, and still deserves a separate no-repo
standalone check if direct script startup is considered part of acceptance.

Long live Codex worker tasks may keep running after the fan-out topology is
validated. Prefer status-mode or focused live smoke when validating runtime
scheduling, and use `blueprint_end` or the workbench API to cancel old live
runs before restarting.

## Skill/Archive Files

Installed skill:

```text
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\runtime-backend\gulicode_bp_standalone_codex_fanout_runtime_2026-06-01.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/gulicode_bp_standalone_codex_fanout_runtime_2026-06-01.md
```
