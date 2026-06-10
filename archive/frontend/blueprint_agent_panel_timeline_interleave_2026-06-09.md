# Blueprint Agent Panel Timeline Interleave

Date: 2026-06-09

## Summary

This archive records the Agent information panel chat timeline fix for the
Blueprint Workbench.

The panel previously projected Agent text and tool calls with an unstable text
upsert key: multiple text parts from the same runtime `message_id` could be
merged into one reply card. The visible result was that Agent replies collected
above the tool-call group, while tool calls collected below, even when the real
stream order was reply, tool call, reply.

The projection now preserves the runtime event order at the panel level:

```text
Agent reply A -> tool-call group -> Agent reply B
```

## Behavior

Text and reasoning entries use `part_id` as the preferred streaming upsert key.
`message_id` is only a fallback because it identifies the broader runtime
message turn, not every visible text block inside that turn.

When a text event arrives before a tool call, the current tool group is flushed.
When a tool event arrives after text, the text block remains in the timeline and
the tool call starts or joins the adjacent tool-call group. Later text with a
new `part_id` becomes a new Agent reply card instead of overwriting or extending
the earlier reply card.

Status-only `message.completed` events without text no longer create empty
Agent reply cards. If a text-bearing event has no `part_id`, the fallback key is
stable and includes `message_id` plus `event_id`, `seq`, or a local fallback
index, which avoids overwriting earlier text blocks from the same `message_id`.

Adjacent tool calls can still merge into one tool-call group. A reply, user
message, or error between tool calls prevents cross-text tool grouping.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Implementation Notes

The relevant projection is `visibleAgentPanelEvents`.

The helper `agentPanelStreamingEntryKey` now resolves keys in this order:

1. `part_id`
2. `message_id + event_id`
3. `message_id + seq`
4. `message_id + fallbackIndex`

The helper `agentPanelTextEventContentText` reads only text payload fields
(`delta` or `text`) for text/reasoning cards. Tool input, tool output, and
status fields remain handled by the tool-call projection and are not reused as
Agent reply body text.

## Verification

Command run from
`F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app`:

```powershell
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
```

Result:

- `23 pass`
- `0 fail`

Additional check:

```powershell
git diff --check -- GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
```

Result:

- passed, with only existing CRLF normalization warnings.

## Packaged Plugin

The personal `gulicode-bp` plugin was rebuilt after the frontend source change.

Packaging command run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package-gulicode-bp-plugin.ps1 -NoSmoke
```

Package summary:

- release directory: `F:\src\Package\Script\Python\multi_agent_tcp\dist\gulicode-bp-0.1.3`
- installed plugin: `C:\Users\qiuhaoxuan\plugins\gulicode-bp`
- summary file: `logs\gulicode-bp-package-ready.json`

The first full packaging attempt ran the smoke path far enough to start the
release service, then failed during cleanup because a log file was still held by
that service process. The temporary process was stopped and the package step was
rerun with `-NoSmoke`.

The plugin workbench stack was then started with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-gulicode-debug.ps1 -NoOpen -SkipPluginInstall
```

Startup artifacts:

- `logs\gulicode-bp-workbench-ready.json`
- collaboration health endpoint returned HTTP 200 at `/api/health`
- workbench, `/mobile`, and `/console` endpoints returned HTTP 200 during the
  post-start checks

