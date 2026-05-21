# Test Agents Communication Priority Archive - 2026-05-22

This archive records the shift back to Test Agent communication validation as
the highest-priority workstream.

## Why This Became Priority

A live blueprint communication test proved that the framework fan-out path can
dispatch from one upstream Test Agent to multiple downstream Test Agents, but
the downstream behavior exposed several alignment gaps:

1. Downstream Agents confused the upstream/source batch id with their own
   current readable batch.
2. Some downstream Agents tried to call `agent_context(batch_id=...)` with an
   upstream `out-*` batch and were correctly denied.
3. A downstream Agent tried to use an outgoing batch id as a `join_id`.
4. Leaf Agents did not consistently treat empty `required_outgoing_targets` as
   the shared-report completion path.

The runtime permission model was not changed: downstream Agents still cannot
read another Agent's batch, and upstream/source batch ids remain provenance or
audit labels.

## Completed Fixes

1. Test Agent panel snapshots now persist one JSON file per blueprint
   `node_id` in the existing `agent-info-panel-tests` directory:
   `agent-panel-test-<safe-node-id>.json`.
2. Saving the same `node_id` overwrites only that Agent's file; saving another
   Test Agent leaves the first file intact.
3. Blueprint start/debug cleanup still clears the whole
   `agent-info-panel-tests` directory at the beginning of a run.
4. Ordinary Agent framework rules and `framework-agent-runtime` now state that
   `framework_context.message_envelope.outgoing_batch_id` is the current batch
   available to the receiving Agent.
5. Framework rules now state that upstream/source `batch_id` values in message
   text are source/audit labels and must not be passed to
   `agent_context(batch_id=...)`.
6. Leaf behavior is now explicit: when `required_outgoing_targets` is empty,
   the Agent should not call `agent_dispatch` or `join_contribute`; it should
   publish receipts/results through `workspace_publish` /
   `workspace_publish_file`.
7. `join_contribute` is now documented as valid only when the framework or
   task explicitly provides a real `join_id`; outgoing batch ids such as
   `out-*` are not join ids.
8. Ordinary MCP errors now include corrective next steps for:
   wrong-batch `agent_context`, no-context/no-batch/wrong-target
   `agent_dispatch`, and unknown or `out-*` `join_contribute`.

## Current Highest Priority

Keep the next testing and debugging loop focused on Agents communication:

1. Run small blueprints with one upstream Test Agent and multiple downstream
   Test Agents.
2. Confirm every required downstream Agent receives its own current batch and
   does not try to read the upstream batch.
3. Confirm every downstream Test Agent has a corresponding per-node JSON panel
   snapshot.
4. Confirm leaf Agents publish shared report receipts/results instead of
   dispatching or joining.
5. Inspect MCP tool-call logs for corrective guidance quality when Agents make
   a wrong call.

## Verification

Repository checks completed before this archive:

```powershell
python -m py_compile agent_launch_context.py blueprint_mcp_runtime.py test_agent_runtime.py test_desktop_blueprint_service.py
pytest -q test_agent_runtime.py::test_graph_runtime_private_context_materializes_codex_skill_and_rules
pytest -q test_desktop_blueprint_service.py::test_run_mcp_ordinary_agent_context_and_join_contribute_are_scope_bound
pytest -q test_desktop_blueprint_service.py::test_run_mcp_agent_dispatch_uses_active_message_scope

cd GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts

cd ..\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
```

## Files Touched By The Supporting Fixes

- `agent_launch_context.py`
- `blueprint_mcp_runtime.py`
- `test_agent_runtime.py`
- `test_desktop_blueprint_service.py`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts`
