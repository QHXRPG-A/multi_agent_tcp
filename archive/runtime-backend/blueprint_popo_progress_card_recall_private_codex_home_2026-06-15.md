# Blueprint POPO Progress Card Recall and Private Codex Home Cleanup

Date: 2026-06-15

## Summary

This archive records the runtime/backend change for framework-owned POPO
progress cards in the `gulicode-bp` plugin.

The goal was to make POPO progress updates transparent to Agents:

- POPO message entry creates one temporary streaming progress card.
- GraphRuntime/Codex stream events update that card with short progress lines
  and temporary Agent text.
- Final user-visible reply deletes the temporary card through POPO recall, then
  sends the final reply through the existing framework POPO reply path.
- Agents do not call POPO tools and do not need to know about the progress
  card transport.

## Progress Card Flow

`DesktopBlueprintService` now keeps in-memory progress state per run:

- `instance_uuid` for the card instance
- POPO `msgId` from `send-msg` response data
- receiver and session type for recall
- stream sequence and last content
- pending visible Agent text deltas

On a POPO session message, the framework creates a card and immediately writes:

```text
思考中...
```

The existing `agent_stream_event_callback` wrapper still wakes Workbench/WebSocket
stream readers, and also maps stream events into POPO progress updates.

Mapped status examples:

- command execution: `正在执行命令...`
- grep/search: `正在搜索代码...`
- file read/open/cat: `正在读取文件...`
- Blueprint ScriptNode: `正在调用脚本节点...`
- Blueprint service: `正在调用服务...`
- generic tool: `正在调用工具 <name>...`

The card uses append-style stream updates. Final content is not written with
`isFinalize=True`; instead the card is recalled before the real final reply is
sent.

## Temporary Agent Replies

Visible Codex `part.delta` text is appended to the progress card as temporary
content under:

```text
Agent 回复
```

This covers intermediate Agent wording such as "第二行已写入，继续最后一行".
Reasoning/thought chunks and stderr chunks are ignored.

`session_event` Agent utterances are treated as temporary unless they look like a
final report or confirmation request. Final-looking replies still use the normal
POPO final reply path.

The final reply path first recalls the temporary card:

```text
POST /open-apis/robots/v1/im/{msgId}/recall
```

Then it sends the final content with the existing `_send_popo_message()` logic.

This avoids the earlier problem where temporary progress text remained visible
above the final answer or where the card stayed in POPO loading state.

## Failure Handling

If the progress stream PUT fails after card creation, the card stays in memory
with its `msgId` and is still recalled when the final reply arrives. This avoids
leaving a loading card behind when a template stream variable update fails.

If recall itself fails, the framework falls back to the existing final POPO reply
transport and records the progress fallback reason in the session transcript.

Run cancellation/termination also best-effort recalls the progress card.

## Codex Loader WARN Cleanup

The POPO card originally displayed warnings such as:

```text
WARN codex_core_plugins::loader: failed to load plugin: plugin is not installed
```

Two fixes were added:

1. POPO progress ignores `part.delta` events with `part_type=stderr`, so Codex
   stderr is never rendered as temporary Agent reply text.
2. `initialize_private_codex_home()` strips `[plugins.*]` sections from the
   copied user `config.toml` for private Agent Codex homes. The isolated
   `codex_home` still inherits runtime auth/model/MCP config, but no longer
   inherits desktop plugin loader state that points at unavailable plugin caches.

This keeps child Agents from trying to load desktop-only plugins such as
`browser@openai-bundled`, `documents@openai-primary-runtime`, or
`gulicode-bp@personal` from an incomplete isolated cache.

Existing already-created run directories are not rewritten; new runs get the
clean private Codex home config.

## Tests

Focused tests from:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

```powershell
python -m py_compile `
  agent_launch_context.py `
  desktop_blueprint_service.py `
  test_agent_runtime.py `
  test_desktop_blueprint_service.py

pytest -q `
  test_agent_runtime.py::test_initialize_private_codex_home_seeds_runtime_state_only `
  test_agent_runtime.py::test_initialize_private_codex_home_maps_legacy_priority_service_tier `
  test_agent_runtime.py::test_initialize_private_codex_home_maps_default_service_tier `
  test_desktop_blueprint_service.py::test_popo_progress_card_appends_visible_agent_delta `
  test_desktop_blueprint_service.py::test_popo_progress_card_streams_thinking_status_and_finalizes `
  test_desktop_blueprint_service.py::test_framework_popo_reply_filters_non_user_visible_utterances
```

Result:

```text
6 passed
```

Earlier focused POPO regression set also passed:

```text
10 passed
```

## Plugin Runtime Verification

The personal plugin was reinstalled/restarted after the code change. The restart
script still returned a non-zero exit code without stdout, but runtime services
were verified directly and the installed package contained the new code.

Verified state after the final restart:

- singleton runtime: `running`, pid `41348`
- runtime URL: `http://127.0.0.1:6034`
- POPO callback: `http://127.0.0.1:3100/health` returned 200
- collaboration: `http://127.0.0.1:8787/api/health` returned 200
- MCP proxy status: `running`
- Workbench URL:

```text
http://127.0.0.1:13438/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default
```

The script exit-code issue appears to be in restart-script lifecycle handling,
not in the runtime services themselves.
