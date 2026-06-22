# Blueprint POPO Table Queue Notifications and Internal Reply Policy

Date: 2026-06-12

## Summary

This archive records the 2026-06-12 runtime/backend change for the
`fill-planning-form` POPO workflow:

- framework-generated script/outgoing reminders now carry an Agent-visible
  no-reply policy
- POPO auto-forwarding suppresses replies produced from those internal
  reminders
- `table_queue` can notify the corresponding Blueprint session when a queued
  table is later occupied
- the planning-table workflow document now requires AISkills lookup before
  choosing a fill-table strategy

The original symptom was that internal messages such as:

```text
Completed. I read the framework rule/skill files...
Completed. Called table_queue_service with action='help'...
```

were sent back to POPO because the start Agent replied to GraphRuntime reminder
messages and `DesktopBlueprintService._forward_framework_popo_reply()` treated
the utterance as a normal POPO-visible Agent reply.

## Internal Reminder Reply Policy

`blueprint_script_call_reminder` and `framework_outgoing_targets_reminder` now
include reply-policy fields at both the message body top level and
`framework_context.message_envelope`:

```json
{
  "reply_required": false,
  "reply_visibility": "framework_internal",
  "framework_message_kind": "blueprint_script_call_reminder"
}
```

For outgoing-target reminders the kind is:

```text
framework_outgoing_targets_reminder
```

The reminder prompt also starts with an explicit instruction that it is a
framework-internal reminder and should not produce a confirmation/status reply
to POPO or the user.

`MCPCurrentMessageContext` and the token scope safe output now expose these
fields, so an Agent inspecting `agent_context` can see the policy directly.

`AgentUtterance` records the reply policy from the triggering message body.
`DesktopBlueprintService._forward_framework_popo_reply()` uses this policy as a
server-side guard and suppresses forwarding when:

- `reply_required` is `false`
- `reply_visibility` is `framework_internal`
- `framework_message_kind` is an internal reminder kind
- legacy reminder message ids start with `script-call-reminder-` or
  `outgoing-targets-reminder-`

Normal POPO user messages are still auto-forwarded when the start Agent replies.

## Table Queue Notification Outbox

The `table_queue` resident service writes a durable notification outbox when
`_process_once()` detects that queued tables are later occupied.

Runtime outbox:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\.state\table_queue_notifications.jsonl
```

Processed-id store:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\.state\table_queue_notifications_processed.json
```

Each notification includes:

- `notificationId`
- `sessionKey`
- `queueId`
- `status`
- `newlyOccupiedTables`
- `pendingTables`
- `allTables`

This avoids relying on the external gateway path, which was not usable in this
environment because `gateway_token_configured=false`.

## Notification Consumer

`DesktopBlueprintService` now has a background table-queue notification watcher
and a manual compensation command:

```text
blueprint.sessions.processTableQueueNotifications
```

The consumer behavior:

- reads unprocessed notification records from the outbox
- finds the Blueprint session by `sessionKey`
- skips deleted or superseded sessions and records a transcript event
- queues directly into the active run when the session is active
- starts a new run from the current Blueprint file when the session is idle or
  terminated but still valid
- sends a `framework_table_queue_notification` to the session's start Agent

The notification intentionally has no outgoing batch and no required script
calls. Its envelope clears:

```json
{
  "required_script_calls": [],
  "required_outgoing_targets": [],
  "remaining_targets": []
}
```

The Agent-facing notification prompt says to continue the already-confirmed
fill-table workflow and not reply only with an acknowledgement. A POPO-visible
reply is expected only for user-visible milestones such as a completion report,
missing information, or a blocking error.

## Planning Table Workflow Rule

The framework planning-table workflow document was updated at:

```text
framework_assets/skills/framework-agent-runtime/planning_table_popo_workflow.md
```

The workflow now requires:

1. Determine whether the POPO message is a fill-table request.
2. Read:

   ```text
   F:\trunk_helper\AISkills\planning-table-skill-index.md
   ```

3. Match the most specific planning-table skill before designing the fill
   strategy.
4. If no suitable skill exists, ask the user whether to continue with the
   framework generic workflow or create/update a dedicated skill first.
5. Do not occupy tables or write table data before the user chooses.

The existing tool boundary remains:

- occupy/release tables only through the `table_queue_service` ScriptNode
- read/write/validate planning tables only through the `xltool` resident
  service

## Plugin Runtime Verification

The plugin was reinstalled/restarted after the code change. One restart command
returned a non-zero exit code without output, but the runtime services were
validated directly afterwards.

Verified runtime state:

- singleton service: `ok`, pid `67192`
- singleton service URL: `http://127.0.0.1:13589`
- collaboration server: `http://127.0.0.1:8787/api/health` returned `ok=true`
- POPO callback: `http://127.0.0.1:3100/health` returned `ok=true`
- Workbench page was reachable on local Vite ports `5173` / `5174`

The manual notification consumer command returned:

```json
{
  "ok": true,
  "delivered": [],
  "skipped": [],
  "errors": [],
  "remaining": 0
}
```

`table_queue` was restarted after the plugin restart so the independent
resident-service process loaded the notification-outbox code:

- old pid: `77792`
- new pid: `22636`
- new port: `1877`

`table_queue.health` returned `notification_file`, confirming the running
service had the outbox-enabled code loaded.

Restarting the plugin invalidated the in-thread `gulicode-bp` MCP stdio
transport. HTTP services were healthy, but the Codex thread needed a plugin/MCP
reconnect before MCP tool calls from that thread would work again.

## Tests

Focused verification from:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

```powershell
python -m pytest -q `
  test_agent_runtime.py::test_graph_runtime_reminds_idle_source_about_remaining_outgoing_targets `
  test_agent_runtime.py::test_graph_runtime_reminds_idle_source_about_required_script_calls `
  test_agent_runtime.py::test_mcp_refresh_message_context_preserves_reply_policy `
  test_agent_runtime.py::test_graph_runtime_private_context_materializes_codex_skill_and_rules `
  test_desktop_blueprint_service.py::test_framework_popo_reply_filters_non_user_visible_utterances `
  test_desktop_blueprint_service.py::test_queue_framework_notification_does_not_create_outgoing_batch `
  test_desktop_blueprint_service.py::test_table_queue_notification_consumer_delivers_to_active_session `
  test_desktop_blueprint_service.py::test_table_queue_notification_consumer_skips_deleted_session
```

Result:

```text
8 passed in 1.20s
```

Compile check:

```powershell
python -m py_compile graph_runtime.py blueprint_mcp_runtime.py desktop_blueprint_service.py plugins/gulicode-bp/mcp/gulicode_bp_mcp.py .multi_agent_workspace\scripts\table_queue_service.py C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\table_queue_service.py
```

Result: exit code `0`.

## Main Files

- `graph_runtime.py`
- `blueprint_mcp_runtime.py`
- `desktop_blueprint_service.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `framework_assets/skills/framework-agent-runtime/planning_table_popo_workflow.md`
- `.multi_agent_workspace/scripts/table_queue_service.py`
- `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\table_queue_service.py`
- `test_agent_runtime.py`
- `test_desktop_blueprint_service.py`

