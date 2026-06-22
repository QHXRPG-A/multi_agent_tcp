# Blueprint Agent Panel, Model Save, and Session Time Polish

Date: 2026-06-11

## Summary

This archive records the Workbench frontend fixes from the 2026-06-11
Blueprint debugging thread.

The main issues were:

- The Agent information panel did not show user messages for POPO-driven runs
  when the durable session timeline was not available.
- Selecting `gpt-5.5` in an Agent node could appear to work but later reopen as
  `gpt-5.4`.
- The Blueprint session dropdown showed only `HH:mm:ss`; users needed full
  year-month-day hour-minute-second precision.

## Agent Panel User Message Projection

`AgentInfoPanel` now passes `panel.info.messageJournal` into the
`visibleAgentPanelEvents()` projection.

When session timeline rows are unavailable, the panel reconstructs user entries
from framework message journal records:

- `framework.message.queued`
- `framework.message.sent`

The projection deduplicates by `messageId`, prefers queued records when both
queued and sent are present, and extracts only the current user message from
prompt envelopes such as:

```text
[Current POPO Message]
[popo_user] ...
```

This avoids displaying the full framework prompt, `Recent BlueprintSession`
context, or prompt-node injected text as if it were a user chat message.

## Agent Model Persistence

Agent field updates in the Inspector now use `updateAgentNode()` and replace the
full draft instead of writing a nested Solid store path directly.

For model changes specifically, the Inspector immediately calls the project
save path after updating the draft. This prevents the selected model from being
lost if the user quickly changes selection, refreshes, or reopens the
Workbench before the debounce timer flushes.

The current `fill-planning-form` planner node was restored to:

```text
model = gpt-5.5
```

The regression test now round-trips an explicit `gpt-5.5` model through
`toBlueprintDocument()` and `fromBlueprintDocument()`.

## Blueprint Session Time Format

The Blueprint session dropdown now formats session timestamps with full local
date and time:

```text
YYYY-MM-DD HH:mm:ss
```

This is intentionally scoped to `BlueprintSessionSelect`. Other runtime status
timestamps still use the shorter `formatRuntimeTime()` display.

## Files Changed

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `.multi_agent_workspace/blueprints/fill-planning-form.json` local state was
  updated so the planner model is `gpt-5.5`.

## Verification

Frontend checks:

```text
bun test GuLiCode\packages\app\src\pages\session\blueprint-side-panel.test.ts
bun test GuLiCode\packages\app\src\pages\session\blueprint-model.test.ts
bun run typecheck
```

Packaging and restart:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package-gulicode-bp-plugin.ps1 -NoSmoke
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-gulicode-debug.ps1 -NoOpen -SkipPluginInstall
```

The packaging command completed successfully. Vite chunk-size/import warnings
and pip temporary-distribution warnings were non-fatal and match previous
packaging runs.

The latest restarted service in this thread:

```text
servicePid = 79088
workbench = http://127.0.0.1:14128/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/fill-planning-form
```

## Follow-up Notes

If this area is touched again, keep these product contracts:

- User-visible chat in the Agent panel should prefer durable session timeline
  rows, then fall back to message journal user records.
- Prompt/context envelopes should not render as standalone user messages.
- Agent model changes should persist immediately, not only through delayed
  autosave.
- Blueprint session-card timestamps should remain full date-time strings.
