# Blueprint POPO File Attachment Delay and Token Refresh

Date: 2026-06-17

## Summary

This archive records the POPO file-only callback fix and the follow-up POPO
robot file-send token fix.

The fixed contract is:

- A POPO message that contains only non-image files is downloaded and cached in
  the callback process, but is not dispatched to Blueprint/Agent immediately.
- The user's next ordinary non-file text message consumes the cached files and
  sends them as `attachments` with that text.
- Consecutive file-only POPO messages accumulate in order.
- Image attachments and text messages with attachments continue to dispatch
  immediately.
- `/new` and `/stop` clear pending files for that POPO conversation.
- `/help` and `/excel-log` neither consume nor clear pending files.
- `blueprint.sessions.message`, `call_blueprint(...)`, `blueprint_send_popo_file`,
  and `file_sender.send(path)` keep their existing public API shape.
- POPO robot file upload now sends `Open-Access-Token` to the returned
  `uploadUrl` and retries once with a fresh token when POPO reports token
  expiry.

Use this record when:

- a POPO file-only message reaches the Agent before the user sends text
- POPO file attachments are shown as unresolved or lack absolute local paths
- POPO file callbacks contain `fileInfo.fileId` but no direct download URL
- multiple POPO files should be delivered with the next text message
- pending POPO files leak between users, groups, robots, or session types
- `/new`, `/stop`, `/help`, or `/excel-log` interacts incorrectly with pending
  files
- `blueprint_send_popo_file` or `file_sender.send(path)` fails with
  `access token expired` even though the local file exists

## Main Files

- `popo_agent_bot_run.py`
- `desktop_blueprint_service.py`
- `test_popo_agent_bot_run.py`
- `test_desktop_blueprint_service.py`
- `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\venv\Lib\site-packages\multi_agent_tcp\desktop_blueprint_service.py`
- `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\venv\Lib\site-packages\multi_agent_tcp\popo_agent_bot_run.py`

## Incoming POPO File Attachments

The POPO callback layer owns the delay behavior. No external or internal
Blueprint session protocol was changed.

POPO file callbacks can arrive with:

```text
notify = <file name>
fileInfo.fileId = <POPO file id>
```

and without a direct downloadable URL. The callback now resolves the file id by
calling:

```text
GET /open-apis/robots/v1/im/file/{fileId}/download
```

with `Open-Access-Token`, reads `data.downloadUrl`, downloads the file bytes,
and stores them under:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\popo_attachments\<yyyyMMdd>\
```

The resulting attachment path is an absolute local filesystem path.

The pending-file cache key includes:

```text
robot_app_key + sender + popo_session_id + popo_group_id + reply_to + session_type
```

This keeps pending files separated across robots, private chats, groups, users,
reply targets, and POPO session types.

## Dispatch Rules

The three POPO callback event branches share the same delivery preparation
logic:

1. Deduplicate the callback event first.
2. Extract and download attachments.
3. Decide whether the callback should cache or dispatch.

File-only means:

- all attachments are `kind=file`
- the raw POPO `notify` is empty, or is only the attached file name/list of file
  names

For file-only messages:

- append the attachments to the pending cache
- return POPO success
- do not start the handler thread
- do not call Blueprint or Agent

For the next ordinary text message:

- pop and clear pending files for the same cache key
- prepend those files to the current `attachments`
- dispatch the text and attachments through the existing
  `blueprint.sessions.message` path

Images are intentionally excluded from this delay behavior because POPO already
supports image+text delivery for the current product path.

## Command Behavior

Reset commands clear pending files:

```text
/new
/stop
```

Read-only/direct commands do not carry pending files and do not clear them:

```text
/help
/excel-log
```

This prevents a cached file from being accidentally delivered as the attachment
for a command request.

The cache is process-local. Restarting the POPO callback service drops any
pending files that have not yet been consumed by a later text message.

## Outgoing POPO File Send Token Fix

`blueprint_send_popo_file(path)` and the `file_sender` resident service both
delegate to the same backend path:

```text
DesktopBlueprintService._send_popo_file_from_mcp(...)
```

The POPO robot send flow is:

1. Register file metadata and receive `fileKey` plus `uploadUrl`.
2. Upload local file bytes to `uploadUrl`.
3. Send the `fileKey` as a POPO `image` or `file` message.

The upload step previously did not pass `Open-Access-Token` to `uploadUrl`.
POPO returned:

```text
errcode = -1
errmsg = access token expired
```

even when the local file existed. The fix sends:

```text
Open-Access-Token: <robot access token>
```

to the upload request as well.

If register, upload, or send raises a token-expired `BlueprintServiceError`, the
service now invalidates the cached robot token and retries the complete
register/upload/send sequence once. This covers both genuinely expired cached
tokens and POPO upload URLs that reject missing or stale token context.

## Verification

Syntax and tests:

```powershell
py -3.13 -m py_compile popo_agent_bot_run.py desktop_blueprint_service.py
py -3.13 -m pytest test_popo_agent_bot_run.py
py -3.13 -m pytest test_desktop_blueprint_service.py -k "blueprint_send_popo_file or file_sender_resident_service"
```

Observed results:

```text
test_popo_agent_bot_run.py: 19 passed
test_desktop_blueprint_service.py selected tests: 5 passed
```

A real POPO callback download smoke verified that `fileInfo.fileId` downloads to
an absolute path under the installed runtime state:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\popo_attachments\20260617\1781690645462_panpan_common.graph
```

A real `check_rule.py` file send smoke verified:

```text
status = succeeded
errcode = 0
fileKey present = true
messageId present = true
path = F:\src\Package\Script\Python\.codex\skills\excel-export-flow\vendor\ExcelToData\check_rule.py
```

The failed pre-fix records for the same file showed
`BLUEPRINT_POPO_FILE_UPLOAD_FAILED` with `access token expired`, confirming that
the failure was the POPO upload credential path, not local file resolution.

## Installed Plugin Notes

After code changes, reinstall/restart with:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\restart-gulicode-bp-plugin.cmd -Install -SkipWebBuild -SyncFrameworkAssets -NoOpen -ProjectDir F:\src\Package\Script\Python\multi_agent_tcp -HealthTimeoutSeconds 90
```

If the restart script exits `1` because of PowerShell confirmation prompts, do
not treat the exit code alone as failure. Confirm the services:

```text
http://127.0.0.1:8787/api/health
http://127.0.0.1:3100/health
```

and open the installed-plugin Workbench through:

```powershell
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\venv\Scripts\python.exe C:\Users\qiuhaoxuan\plugins\gulicode-bp\scripts\start_workbench.py --project-dir F:\src\Package\Script\Python\multi_agent_tcp --blueprint-id fill-planning-form --ready-file C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\logs\gulicode-bp-workbench-ready.json
```

Do not use a stale `gulicode-bp-workbench-ready.json` URL without an HTTP check;
the file can point to a dead Workbench port after a restart.
