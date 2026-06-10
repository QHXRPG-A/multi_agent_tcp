# Blueprint Table Queue Script Help Pattern

Date: 2026-06-08

## Summary

This archive records the current `table_queue_service` Script Function Node
pattern and makes it the reference pattern for future Blueprint ScriptNode help
contracts.

Use this record when:

- building a ScriptNode that multiplexes behavior with `action` + `arguments`
- hiding a resident service behind a script-only gateway
- deciding how an Agent should discover nested argument schemas
- debugging table occupation, valid table name validation, or table list refresh

## Current Files

Project ScriptNode:

```text
F:\src\Package\Script\Python\multi_agent_tcp\.multi_agent_workspace\scripts\table_queue_service.py
```

Global resident service:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\table_queue_service.py
```

Resident service state:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\.state\table_queue_queue.json
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\.state\table_queue_valid_tables.json
```

Valid planning-table directory:

```text
F:\src\Package\Script\Python\.codex\skills\excel-export-flow\vendor\trunk\策划表格
```

## ScriptNode Help Contract

The `table_queue_service` ScriptNode uses this public entrypoint shape:

```json
{
  "action": "occupy",
  "arguments": {}
}
```

For future ScriptNodes that use `action` + `arguments`, follow this pattern:

- Keep the function signature simple: `action: str`, `arguments: dict`.
- Define a `SERVICE_ACTIONS` or equivalent allowlist for real service actions.
- Define `HELP_ALIASES = {"help", "schema"}`.
- Define one `ACTION_HELP` entry per important action.
- `help/schema` with a valid target returns only that target schema.
- `help/schema` with no target returns all schemas.
- Unknown business actions return `TABLE_QUEUE_ACTION_NOT_ALLOWED`-style errors
  with `allowed_actions` and a short hint, but do not return all schemas.
- Normal business actions never include `ACTION_HELP` in their result.

Example targeted help call:

```json
{
  "action": "help",
  "arguments": {
    "action": "occupy"
  }
}
```

Equivalent:

```json
{
  "action": "schema",
  "arguments": {
    "target": "refresh_valid_tables"
  }
}
```

Expected result shape:

```json
{
  "ok": true,
  "script": "table_queue_service",
  "usage": "Call this ScriptNode with action plus arguments. Inspect schemas for action-specific fields.",
  "actions": ["health", "occupy", "release"],
  "help_actions": ["help", "schema"],
  "schemas": {
    "occupy": {
      "description": "...",
      "required_arguments": ["userId", "sessionKey", "email", "tableNames"],
      "optional_arguments": ["trunk", "channel"],
      "arguments": {},
      "example": {}
    }
  }
}
```

## Covered Table Queue Schemas

`ACTION_HELP` currently documents these table queue actions:

- `occupy`
- `release`
- `queue_status`
- `cancel`
- `process_once`
- `occupy_list`
- `health`
- `refresh_valid_tables`

The script also permits maintenance actions:

- `valid_tables`
- `set_valid_tables`
- `add_valid_tables`
- `remove_valid_tables`

Those maintenance actions can be documented later if Agents need to operate
them directly.

## Table Queue Behavior

`table_queue` is a script-only resident service. Ordinary Agents should not call
it directly through resident service tools. They should call the
`table_queue_service` ScriptNode through `blueprint_script_call`.

Primary service actions:

- `health`: returns queue file, valid table list file, valid table count, remote
  API summary, and SVN update timeout.
- `occupy`: validates table names, checks self-occupied tables, tries remote
  occupation once, queues unavailable tables, and sends notification when
  possible.
- `release`: validates table names and releases one or more full `.xlsx` names.
- `occupy_list`: queries the remote self table list for one email.
- `queue_status`: reads queued occupation requests.
- `cancel`: removes a queued request without releasing already occupied tables.
- `process_once`: polls queued requests by checking self occupation state only;
  it does not call remote `table_occupy` again.
- `refresh_valid_tables`: runs SVN update by default, then scans `.xlsx` files
  into the valid table list.

## Valid Table Name Guard

The service maintains a valid table name list in:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\.state\table_queue_valid_tables.json
```

`occupy` and `release` call the validation guard before touching the remote
table service. If a requested table is not in the valid list, the service
returns:

```json
{
  "ok": false,
  "code": "INVALID_TABLE_NAME",
  "invalidTables": ["..."],
  "suggestions": {}
}
```

If the valid table list is missing or empty, the service returns:

```json
{
  "ok": false,
  "code": "VALID_TABLE_LIST_NOT_CONFIGURED"
}
```

## Refresh and SVN Update

`refresh_valid_tables` defaults to:

```json
{
  "action": "refresh_valid_tables",
  "arguments": {
    "recursive": false,
    "svnUpdate": true
  }
}
```

The service runs:

```powershell
svn update F:\src\Package\Script\Python\.codex\skills\excel-export-flow\vendor\trunk\策划表格
```

Then scans non-temporary `.xlsx` files. Temporary files beginning with `~$` are
ignored.

Set `svnUpdate: false` only when intentionally skipping update.

## Verification

Verified from:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

Compile checks:

```powershell
python -m py_compile "C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\table_queue_service.py" ".multi_agent_workspace\scripts\table_queue_service.py"
```

Script catalog:

```text
table_queue_service.py:table_queue_service
```

Help coverage smoke:

```text
occupy, release, queue_status, cancel, process_once, occupy_list, health, refresh_valid_tables
missing=[]
```

Live service refresh:

```text
table_queue pid=60048
refresh_valid_tables ok=true
svn update returncode=0
updated to revision 3300833
valid table count=302
```

Health result included:

```text
valid_tables_configured=true
valid_table_count=302
valid_tables_source=directory:F:\src\Package\Script\Python\.codex\skills\excel-export-flow\vendor\trunk\策划表格
svn_update_timeout_seconds=120.0
```

## Future Rule

For future ScriptNodes that expose more than one operation, use
`table_queue_service` as the help/schema reference design:

1. Agent-facing contract lives in the ScriptNode, not only in the resident
   service.
2. The ScriptNode supports `help` and `schema`.
3. Targeted help returns one schema to keep Agent context small.
4. Empty help returns all schemas for discovery.
5. Unknown actions return allowed actions plus a hint, not a full schema dump.
6. Business calls return only business results.
