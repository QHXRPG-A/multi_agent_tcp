# Blueprint Resident Services, Script Nodes, and xltool Live Smoke

Date: 2026-06-08

## Summary

This archive records the current boundary between Blueprint Script Function
Nodes and global Blueprint resident services, plus the live `xltool` resident
service smoke test run through a real AgentNode.

Use this record when debugging:

- how AgentNodes discover and call resident services
- who owns resident service descriptions
- whether service calls return results synchronously
- how Script Function Nodes differ from resident services
- the `xltool` planning-table service smoke against a real Excel workbook

## Script Function Nodes

Script Function Nodes are project-scoped transformation steps. They live under
the project workspace script directory:

```text
<project>/.multi_agent_workspace/scripts/
```

The framework generates a local script-author API shim:

```text
<project>/.multi_agent_workspace/scripts/gulicode_blueprint.py
```

Script authors import `blueprint_node` from that shim and mark Python functions
as Script Function Nodes. Discovery and validation are handled by
`blueprint_script_nodes.py`; graph definitions persist them in
`GraphDefinition.script_nodes`.

Runtime behavior:

- ScriptNodes remain transparent transformation steps in graph traversal.
- ScriptNodes are project-local, not global plugin services.
- Agents do not start or stop ScriptNodes.
- When a downstream Agent needs a script output, the framework prompts the
  Agent through required script-call context and exposes `blueprint_script_call`.
- Script execution returns structured outputs to connected downstream nodes.

Primary files:

- `blueprint_script_nodes.py`
- `graph_runtime.py`
- `desktop_blueprint_service.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`

## Resident Services

Resident services are global long-lived Python services owned by the
`gulicode-bp` plugin runtime state, not by a single project:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services
```

The framework generates this service-author API shim:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\gulicode_blueprint_service.py
```

Service authors mark a class with `@blueprint_service(...)` and expose methods
with `@service_method(...)`. Discovery, docs, lifecycle, RPC, and logs are
handled by `blueprint_resident_services.py`.

Runtime behavior:

- Workbench/Codex MCP may list, create, start, stop, open, and read logs/docs for
  resident services.
- Ordinary AgentNode tools cannot start or stop services.
- Agent launch context includes `framework_context.resident_services`, listing
  visible services by name, description, status, and method summary.
- Agents inspect method signatures with `blueprint_service_docs(service_name)`.
- Agents call a method with
  `blueprint_service_call(service_name, method_name, arguments)`.

Primary files:

- `blueprint_resident_services.py`
- `agent_launch_context.py`
- `blueprint_mcp_runtime.py`
- `desktop_blueprint_service.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`

## Description Ownership

The resident service `description` is service-author metadata.

For generated services, `blueprint_create_resident_service` writes the initial
description into the service template. After that, the source file is the source
of truth through the `@blueprint_service(name=..., description=...)` decorator.
Discovery reads that decorator metadata and passes it into Workbench panels and
Agent launch context.

For the `xltool` service tested here, the description was set in:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\xltool_service.py
```

Current description:

```text
策划表 xltool 常驻服务：按字段意义读写 Excel 策划表，隐藏列号和坐标细节。
```

## Service Call Return Semantics

From the Agent's perspective, `blueprint_service_call(...)` is synchronous: the
tool call returns after the resident service method finishes or times out. If a
method is slow, the Agent waits for that method result before receiving the tool
return value.

For long-running service work, the service should expose an async-style contract
itself, for example:

- `start_job(...) -> {job_id}`
- `get_job_status(job_id)`
- `get_job_result(job_id)`
- optional cancel/cleanup methods

Without that pattern, a long-running method blocks the Agent tool call until
completion or timeout.

## xltool Service Shape

The `xltool` service is a global resident service wrapping
`D:\excelize-cli\bin\xltool.exe` for semantic planning-table Excel operations.

Important service behavior after the 2026-06-08 service update:

- `read_row_by_field`, `query_rows`, and `diff_by_key` default `header_row` to
  `0`, allowing xltool to auto-detect the planning-table header block.
- `ID` should be interpreted as the planning-table semantic field, not an Excel
  coordinate column.
- `set_row` writes by semantic field name.
- Convenience methods include `append_row`, `set_cells`, `dry_run`,
  `validate_key`, and `list_fields`.

## Live Agent Smoke

Target workbook:

```text
D:\excelize-cli\6-0-技能表.xlsx
```

Target sheet:

```text
技能表
```

Live Blueprint run:

```text
run-85ab3e4380b5
```

Smoke path:

1. Agent confirmed `xltool` was visible in `framework_context.resident_services`.
2. Agent called `blueprint_service_docs("xltool")`.
3. Agent called `blueprint_service_call("xltool", "read_row_by_field", ...)`
   with `ID=1.1`.
4. Service returned `matched_row=8`.
5. Agent called `blueprint_service_call("xltool", "set_row", ...)` to write:

```text
row: 8
field: 技能描述
value: agent_xltool_smoke_20260608
```

6. Agent called `read_row_by_field` again and verified the value.
7. An external direct xltool read also verified:

```text
H8 = agent_xltool_smoke_20260608
```

Service write result:

```text
ok=true
exit_code=0
changed=true
```

Backups created/kept:

```text
D:\excelize-cli\6-0-技能表.agent-backup-20260608.xlsx
D:\excelize-cli\6-0-技能表.xlsx.bak.20260608113137.xlsx
```

## Observations

- WPS/Excel file locks block in-place writes. The first live smoke reached the
  service but failed to write while the workbook was open. After closing WPS,
  the same real-Agent path succeeded.
- Service method results are returned to the Agent tool call. The framework also
  queues service-result messages back into the Agent runtime, which can trigger
  additional follow-up turns if the Agent prompt does not explicitly treat them
  as terminal/no-op context.
- Ending `run-85ab3e4380b5` hit a framework archive/close issue on Windows deep
  paths (`WinError 3` / `WinError 206`). The Agent task and xltool write
  succeeded, but final run archive status was marked failed by the close/archive
  step. This is a framework close-loop issue, not a resident service write
  failure.
- The leftover test Agent child process was stopped manually after the smoke.
  The `xltool` resident service itself remained running.

## Verification

Commands/results verified from:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

Resident service status:

```text
blueprint_resident_services()
```

Result:

```text
xltool status=running pid=27088 port=10715
```

Direct workbook read-back:

```powershell
& 'D:\excelize-cli\bin\xltool.exe' read-row-by-field --file 'D:\excelize-cli\6-0-技能表.xlsx' --sheet '技能表' --header-row 0 --field 'ID' --value '1.1' --coordinates
```

Result:

```text
ok=true
matched_row=8
技能描述=agent_xltool_smoke_20260608
H8=agent_xltool_smoke_20260608
```

## Follow-ups

- Fix Blueprint run close/archive handling for deep Windows paths so successful
  runs are not reported as failed during archive movement.
- Decide whether service-result callback messages should be terminal by default
  for ordinary service calls, or whether Agent prompts must always handle them.
- For long-running resident service methods, prefer explicit job/poll APIs
  rather than blocking `blueprint_service_call` for the whole operation.
