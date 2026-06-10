# Blueprint POPO Reply Tool and Readable Sessions

Date: 2026-06-09

## Summary

This archive records the runtime/backend work that lets a POPO-started
Blueprint start full Agent reply directly to the originating POPO user through
a private run-scoped MCP tool.

It also records the follow-up session identity fix: POPO private sessions now
use a readable `bps_popo_<user>_<hash>` key instead of an opaque
`bps_<hash>` key, so Workbench session lists show which POPO user owns the
conversation.

## MCP Reply Tool

The run-scoped ordinary MCP tool is:

```text
blueprint_reply_popo_user(content: str)
```

Only `content` is accepted. The Agent cannot pass a receiver, token,
`robotAppKey`, app secret, or callback credential.

Tool visibility and call authorization are intentionally narrow:

- The current run must be a POPO Blueprint session.
- The caller must be the saved start full AgentNode for that run.
- The run must be bound to an active Blueprint session.
- The active session must match the run and robot binding.

`RunMCPRuntimeHandle.enable_popo_user_reply(...)` enables the tool for the
start Agent's ordinary token. `DesktopBlueprintService._reply_popo_user_from_mcp`
performs the authoritative checks and sends the POPO message.

The tool is pre-enabled for a POPO-capable start Agent when a live runtime is
created, because an already-launched Codex Agent may not refresh its MCP tool
list after a later POPO message binds the slot to a concrete session. Actual
sending still fails unless the active POPO session binding exists.

## Receiver Ownership

The POPO callback process passes session identity through `sessionIdentity`:

- `popoUserId`
- `popoSessionId`
- `popoGroupId`
- `popoReplyTo`
- `popoSessionType`

`DesktopBlueprintService.message_blueprint_slot(...)` persists these fields on
the Blueprint session. When the Agent calls `blueprint_reply_popo_user`, the
service derives the receiver in this order:

```text
popoReplyTo
popoGroupId
popoUserId
popoSessionId
```

This means the Agent does not need to infer whether the message came from POPO
or which POPO user should receive the reply. Seeing the tool means the current
run has POPO reply capability; the service owns the target.

Successful sends append both transcript events:

- `agent_reply`
- `popo_reply_sent`

This distinguishes "Agent produced a reply" from "POPO API send was called" in
later diagnostics.

## POPO Send Helper

The service now owns a lightweight POPO API path instead of importing the Flask
callback app.

The helper:

- Gets and caches a robot access token from
  `open-apis/robots/v1/token`.
- Sends text through `open-apis/robots/v1/im/send-msg`.
- Resolves robot credentials from the saved global callback robot config.
- Does not return or expose receiver, token, or secrets to the Agent.

Errors are mapped to stable `BlueprintServiceError` codes such as
`BLUEPRINT_POPO_TOKEN_FAILED`, `BLUEPRINT_POPO_SEND_FAILED`, and
`BLUEPRINT_POPO_REPLY_TARGET_REQUIRED`.

## Readable POPO Session Keys

POPO Blueprint sessions now generate keys like:

```text
bps_popo_qiuhaoxuan-corp.netease.com_1c718047678a3180a07553de
```

The readable label comes from POPO identity:

- Private chats prefer `popoUserId`.
- Group sessions include group and user when both are available.
- The trailing 24-character hash remains the stable uniqueness guard.

The older opaque key format remains accepted:

```text
bps_<24 hex chars>
```

When `blueprint.sessions.list` or a later POPO message sees an old POPO
session, the service migrates the directory and `session.json` to the readable
key and updates any in-memory run/session bindings.

`sessionDisplayName` is also stored, for example:

```text
POPO qiuhaoxuan@corp.netease.com
```

## Main Files

- `blueprint_mcp_runtime.py`
- `desktop_blueprint_service.py`
- `popo_agent_bot_run.py`
- `test_desktop_blueprint_service.py`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python -m py_compile blueprint_mcp_runtime.py desktop_blueprint_service.py popo_agent_bot_run.py test_desktop_blueprint_service.py
python -m pytest test_desktop_blueprint_service.py -q -k "popo_reply or popo_slot_message_without_project_dir or popo_callback_health or popo_termination_tool or popo_reply_tool or live_slot_start_ensures_start_agent or queue_agent_message_ensures_agent"
python -m pytest test_desktop_blueprint_service.py -q -k "popo or slot or session_message or run_mcp"
python -m pytest test_desktop_blueprint_service.py -q -k "popo or session_message or sessions"
python -m pytest test_graph_control.py -q
git diff --check
```

Results:

- Python compile passed.
- Focused POPO reply tests passed: `7 passed, 104 deselected`.
- Broader slot/session/MCP tests passed: `37 passed, 74 deselected`.
- POPO/session tests after readable-key work passed: `23 passed, 90 deselected`.
- Graph control tests passed: `27 passed`.
- `git diff --check` passed with only existing CRLF warnings.

Plugin packaging and runtime checks:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
```

The plugin rebuild and wheel install completed with `ok: true`. The runtime was
restarted through the personal plugin workbench wrapper.

Final running service check after restart:

- Workbench:
  `http://127.0.0.1:14467/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default`
- Runtime service: `http://127.0.0.1:14592`
- Runtime pid: `21680`
- POPO callback service pid: `34940`
- POPO callback service port: `3100`

`blueprint.sessions.list` returned the migrated readable session:

```text
bps_popo_qiuhaoxuan-corp.netease.com_1c718047678a3180a07553de
```

