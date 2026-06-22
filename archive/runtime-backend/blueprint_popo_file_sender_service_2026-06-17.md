# Blueprint POPO File Sender Service

Date: 2026-06-17

## Summary

This archive records the framework-level POPO file/image sender added for
Blueprint Agent runs.

The new contract is:

- Ordinary Agents can call `blueprint_send_popo_file(path)`.
- The Agent only passes a local file path.
- The framework resolves the current Blueprint session's POPO receiver and
  robot app key from the active run/session context.
- The service sends `.jpg`, `.jpeg`, `.gif`, `.png`, and `.bmp` as
  `msgType=image`; all other files are sent as `msgType=file`.
- Files must exist, be regular files, and stay within the POPO 20 MB limit.
- Non-POPO sessions, missing receivers, missing robot config, invalid paths,
  oversized files, and POPO API failures return explicit errors and write
  failed send records.

Use this record when:

- an Agent cannot see or call `blueprint_send_popo_file`
- `file_sender.send(path)` does not route through the framework
- file/image send records are missing under a Blueprint session
- POPO file sends require receiver, robot, token, or credential arguments from
  the Agent
- `blueprint.sessions.fileSendHistoryList` or
  `blueprint.sessions.fileSendHistory` returns `UNKNOWN_COMMAND`
- a packaged plugin runs stale runtime code after adding the file sender

## Main Files

- `desktop_blueprint_service.py`
- `blueprint_mcp_runtime.py`
- `graph_control.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `framework_assets/resident_services/file_sender_service.py`
- `framework_assets/skills/framework-agent-runtime/SKILL.md`
- `framework_assets/skills/framework-worker-runtime/SKILL.md`
- `framework_assets/rules/framework-agent-runtime.md`
- `framework_assets/rules/framework-worker-runtime.md`
- `sync-gulicode-bp-framework-assets.ps1`
- `test_desktop_blueprint_service.py`
- `test_graph_control.py`
- `test_agent_runtime.py`

## POPO Send Flow

The framework uses the official robot file flow:

1. Register file metadata through:

   ```text
   POST /open-apis/robots/v1/im/file
   ```

   with `fileType`, `fileName`, and `fileMd5`.

2. Read `fileKey` and `uploadUrl` from the response.
3. Upload the local file to `uploadUrl` with `multipart/form-data`.
4. Send the message through:

   ```text
   POST /open-apis/robots/v1/im/send-msg
   ```

   using:

   ```json
   {
     "msgType": "image | file",
     "message": { "fileKey": "..." }
   }
   ```

The implementation reuses existing robot token/config resolution and POPO
session metadata. It does not expose robot credentials to Agents.

## MCP Tool

`RunMCPRuntimeHandle` now exposes an ordinary-message tool:

```text
blueprint_send_popo_file(path: str)
```

The tool is included in the ordinary Agent tool allowlist and delegates to the
runtime callback registered by `DesktopBlueprintService`.

The callback records the calling Agent node id and Agent id when available.

## Resident Service

The resident service source file is:

```text
framework_assets/resident_services/file_sender_service.py
```

Stable service name:

```text
file_sender
```

UI title:

```text
传文件服务
```

Description:

```text
将相关路径下的文件或图片传给当前会话的用户
```

The service exposes:

- `help(action: str = "")`
- `send(path: str)`
- `history(limit: int = 50)`

`help` follows the `table_queue_service` style:

- empty action returns all method schemas
- known action returns one method schema
- unknown action returns `allowedActions` plus a hint

Live GraphRuntime service calls to:

```text
blueprint_service_call("file_sender", "send", {"path": "..."})
```

are intercepted by `GraphRuntimeControlPlane` and delegated to the same
framework callback as `blueprint_send_popo_file`.

The standalone resident-service process keeps documentation wrappers only; the
actual send requires the framework callback so Agents do not pass receiver or
robot context.

## Persistent Records

Records are written per Blueprint session:

```text
blueprint_sessions/<sessionKey>/file_sends/*.json
```

Each record includes:

- schema version and record id
- time and timestamp
- session key, run id, source node id, and Agent id
- source path, file name, extension/type, and byte size
- POPO `messageType`
- receiver and robot app key
- status
- POPO `errcode`, `errmsg`, `fileKey`, and message id when available
- framework error code/message for failures

`blueprint.sessions.clear` now removes both:

```text
excel_ops
file_sends
```

## History APIs

`DesktopBlueprintService.handle_request` now supports:

```text
blueprint.sessions.fileSendHistoryList
blueprint.sessions.fileSendHistory
```

The `gulicode-bp` MCP command allowlist includes both commands as read-only
Workbench-facing APIs.

The list endpoint mirrors the Excel history shape:

- only visible sessions for the current project/blueprint are returned
- deleted/superseded sessions are hidden
- sessions are sorted by latest send time descending

## Packaging and Installed Runtime Notes

The service file is copied by:

```powershell
.\sync-gulicode-bp-framework-assets.ps1
```

into:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\resident_services\file_sender_service.py
```

The sync script validates that `file_sender_service.py` exists after sync.

During this work, the installed plugin runtime venv had stale/broken pip state
around `pywin32` and temporary `~...` package directories. A clean repair path
was:

1. Stop plugin-owned Python processes and old `multi_agent_tcp broker/agent`
   processes holding runtime files open.
2. Remove the damaged plugin runtime venv while preserving `.runtime\state`.
3. Recreate the venv with Python 3.13.
4. Install the current plugin wheel into the venv.
5. Sync framework assets and start the installed plugin Workbench.

The final runtime import check confirmed:

```text
tool_allowed True
runtime_has_callback True
service_has_send True
file_sends_text True
```

## Verification

Focused checks run from:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

Commands:

```powershell
py -3.13 -m py_compile desktop_blueprint_service.py blueprint_mcp_runtime.py graph_control.py blueprint_resident_services.py framework_assets\resident_services\file_sender_service.py plugins\gulicode-bp\mcp\gulicode_bp_mcp.py
py -3.13 -m pytest test_desktop_blueprint_service.py -k "file_send or run_mcp_blueprint_send_popo_file or full_agent_message_only_context or gulicode_bp_mcp_planning or sessions_clear_terminates"
py -3.13 -m pytest test_graph_control.py -k "file_sender_service_send or resident_service_call_can_return_without_queueing_result"
py -3.13 -m pytest test_agent_runtime.py -k "full_worker_json or full_agent_indexes_heavy_business_skill_without_copying_payloads"
```

Results:

- py_compile passed
- `test_desktop_blueprint_service.py`: 4 passed
- `test_graph_control.py`: 2 passed
- `test_agent_runtime.py`: 1 passed

Health checks after installed runtime repair:

```text
http://127.0.0.1:8787/api/health -> 200
http://127.0.0.1:3100/health -> 200
```

Current Workbench ready URL observed during verification:

```text
http://127.0.0.1:1637/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default
```

The in-thread `gulicode-bp` MCP transport returned `Transport closed` after the
plugin restart. This is expected after restarting the MCP service from the same
Codex thread; the HTTP services were healthy.

## Integration Gap

The code path was unit-tested with fake POPO APIs and installed-runtime import
checks. A real POPO send smoke still requires an active POPO-bound Blueprint
session and should call:

```text
blueprint_send_popo_file(path)
```

from that live Agent context.
