# Blueprint Sessions, Run Slots, POPO Entry, and MCP Boundaries

Date: 2026-06-05

## Summary

This archive records the Blueprint session and run-slot refactor for the
`gulicode-bp` Codex plugin runtime. The new model separates lightweight
external conversation context from live Agent/Codex processes:

- `BlueprintSession` stores context, identities, recent messages, `activeRunId`,
  and `lastRunId`; it is not a process.
- A "Blueprint run slot" is a user-started live run that can later receive UI
  or POPO messages at the saved start AgentNode.
- POPO and UI message entry no longer create runs implicitly.
- Codex desktop may still help the user set the start AgentNode and execute an
  explicit plan, but those are two separate actions.

## Runtime Behavior

- Blueprint documents preserve `runtime.start_node_id`.
- The saved start node must reference exactly one AgentNode.
- `runtime.popo_entry` is persisted in the blueprint document and must be
  enabled and complete before starting a run slot.
- `BlueprintSession` records live under:

```text
CODEX_HOME/gulicode-bp/state/blueprint_sessions/<sessionKey>/
```

- Session context is persisted in `session.json` and `transcript.jsonl`.
- Session cold-start context is built from `contextSummary` plus recent
  transcript messages, capped at 12k characters.
- Run completion clears runtime temporary state such as `activeRunId` while
  preserving session context for future starts.
- The global live-run cap for Blueprint session slots is three.

## Run Slots

- `blueprint.slots.start` creates an idle live run slot only after preflight:
  common config paths, valid AgentNode start node, complete POPO entry, robot
  structure uniqueness, and global slot limit.
- `blueprint.slots.message` does not create runs. It routes messages to an
  existing session's active run or assigns a new session to a matching idle slot.
- Idle slot assignment prefers the matching pool and then least-recently-touched
  slots.
- Assigned slots bind to one session until the run reaches a terminal state.
- POPO robot bindings use the robot app key and structure id to avoid ambiguous
  routing.

## Codex Desktop Commands

The previous "Codex creates plan and chooses start node" behavior was split:

- `blueprint.runtime.setStartAgent` saves the start AgentNode without starting a
  run.
- `blueprint.runtime.executePlan` validates and executes a caller-provided plan
  against the saved start AgentNode.

`executePlan` rejects any plan whose `start_nodes` differ from the saved
`runtime.start_node_id`, and forces `run_policy.requires_confirmation = false`
for direct execution.

## MCP Boundary

Public Codex MCP remains focused on direct user-authorized control and
monitoring:

- Exposed:
  - `blueprint_set_start_agent`
  - `blueprint_execute_plan`
  - list/status/events/diff/agent_info/queue diagnostics and existing CRUD
- Not exposed:
  - `blueprint.slots.start`
  - `blueprint.slots.message`
  - `blueprint.popo.config`
  - old public plan-create/plan-validate/start tool functions

`blueprint.slots.*` and `blueprint.popo.config` are internal service commands.
Workbench can call the slot commands through its local token-protected
`/api/blueprint` bridge; Codex MCP cannot call them through `blueprint_request`.

During automation, a real integration gap was found and fixed:

- Workbench `/api/blueprint` originally forwarded `blueprint.slots.start` through
  the public allowlist, returning `UNKNOWN_COMMAND`.
- The bridge now detects `INTERNAL_COMMANDS` after workbench token validation and
  calls `DesktopBlueprintService.handle_request` directly.
- After the fix, `blueprint.slots.start` reaches service preflight and correctly
  returns `BLUEPRINT_POPO_ENTRY_REQUIRED` when the default blueprint lacks an
  enabled POPO entry.

## AgentNode Monitor Tools

Full AgentNode launch context now supports
`access_policy.blueprint_monitor_tools`, defaulting to `false`.

When enabled for a run-local full Agent, the private MCP runtime can expose
read-only current-run tools:

- `blueprint_current_status`
- `blueprint_current_events`
- `blueprint_current_agent_info`
- `blueprint_current_run_diff`

These tools are scoped to the current run and do not accept arbitrary run ids.
They do not expose plan/start/slot/end/rollback/delete/session mutation actions.

## POPO Bot

The POPO bot path no longer shells out to `codex exec` or `codex resume`.

It now:

- Uses callback routes with the robot app key in the path.
- Resolves robot config from saved blueprint `runtime.popo_entry`.
- Calls the `gulicode-bp` singleton service internal slot-message command.
- Maps p2p/group/session identity into the Blueprint session key.
- Returns clear errors for missing robot binding, incomplete config, missing
  slots, full slots, busy state, timeout, and terminal responses.

## Main Files

- `desktop_blueprint_service.py`
- `graph_runtime.py`
- `agent_launch_context.py`
- `blueprint_mcp_runtime.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `plugins/gulicode-bp/scripts/smoke_standalone_plugin.py`
- `popo_agent_bot_run.py`
- `test_desktop_blueprint_service.py`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp` unless noted:

```powershell
python -m py_compile desktop_blueprint_service.py graph_runtime.py agent_launch_context.py blueprint_mcp_runtime.py plugins\gulicode-bp\mcp\gulicode_bp_mcp.py popo_agent_bot_run.py
pytest test_desktop_blueprint_service.py -q
```

Frontend-related checks from `GuLiCode/packages/app`:

```powershell
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build
```

Plugin refresh and workbench smoke:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force --skip-web-build
```

Manual/browser/service checks:

- Restarted the stale singleton service so the installed runtime picked up the
  new wheel and MCP bridge.
- Loaded Workbench from the refreshed singleton service.
- Verified `blueprint.runtime.setStartAgent` saves `runtime.start_node_id =
  agent`.
- Verified `blueprint.runtime.executePlan` rejects mismatched `start_nodes`.
- Verified public `blueprint_request` rejects `blueprint.slots.start`.
- Verified Workbench API internal `blueprint.slots.start` reaches service
  preflight and returns `BLUEPRINT_POPO_ENTRY_REQUIRED`.
- Verified `blueprint_list_runs` returns no residual live runs after testing.

## Notes

- The installed plugin venv emitted repeated pip "invalid distribution" warnings
  from stale temporary directories, but installer output returned `ok: true` and
  runtime imports/tests passed.
- Full positive slot-start smoke was intentionally not run because the default
  blueprint has incomplete POPO config and a positive start would launch live
  Agent/Codex processes.
- The default blueprint was left with `runtime.start_node_id = "agent"` as part
  of set-start validation.
