# Blueprint Sessions, Run Slots, and POPO Entry UI

Date: 2026-06-05

## Scope

This archive records the Workbench UI changes for Blueprint sessions, run
slots, start-Agent selection, POPO robot entry configuration, and Agent monitor
tool toggles. Runtime/backend details are archived separately in
`archive/runtime-backend/blueprint_sessions_slots_popo_mcp_2026-06-05.md`.

## Top Toolbar Sessions

- Added a Blueprint sessions dropdown next to the Blueprint selector.
- The trigger displays the running session count, for example `会话 0`.
- The dropdown shows running and recent sessions, with running sessions sorted
  first.
- Session list cards expose:
  - session id
  - blueprint name/id
  - status
  - delete action
- Running sessions cannot be deleted; idle sessions are soft-deleted.
- The list container uses a fixed max height and `overflow-y: auto`, so up to
  eight visible panels can be browsed with scrolling.
- Empty state uses the dedicated "no Blueprint sessions" copy.

Important selectors:

- `data-blueprint-session-select`
- `data-blueprint-session-dropdown`
- `data-blueprint-session-list`
- `data-blueprint-session-card`
- `data-blueprint-session-delete`

## Runtime Panel

- Runtime panel terminology changed from direct run to "Blueprint run slot".
- Start node selection is a single-select control.
- The start-node list only includes AgentNode entries.
- The runtime panel no longer exposes the old task textarea or plan-generation
  UI.
- The slot start button saves the document first, then calls
  `platform.startBlueprintSlot`.
- The slot message input sends to the current run slot through
  `platform.sendBlueprintSlotMessage`.

Important selectors:

- `data-blueprint-runtime-start-node-select`
- `data-blueprint-runtime-confirm-run`
- `data-blueprint-runtime-slot-message`
- `data-blueprint-runtime-slot-message-submit`

## Inspector

- The start AgentNode inspector displays POPO robot entry settings.
- Non-start AgentNodes do not expose editable POPO entry configuration.
- POPO entry fields are persisted in `runtime.popo_entry`:
  - `enabled`
  - `robot_app_key`
  - `robot_name`
  - `robot_app_secret`
  - `callback_token`
  - `aes_key`
- Full AgentNode access policy includes an independent "Blueprint monitor tools"
  toggle, backed by `access_policy.blueprint_monitor_tools`.
- The new monitor-tools flag defaults to `false` in documents and runtime model
  normalization.

## Platform Bridge

The app platform gained:

- `listBlueprintSessions`
- `deleteBlueprintSession`
- `sendBlueprintSessionMessage`
- `startBlueprintSlot`
- `sendBlueprintSlotMessage`

The plugin Workbench bridge is responsible for translating slot start/message
calls into internal service commands. A smoke test found that the bridge
initially returned `UNKNOWN_COMMAND` for `blueprint.slots.start`; the bridge was
fixed to route internal commands after local token validation.

## Main Files

- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/entry.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Browser Smoke

Workbench was refreshed through the personal plugin installer and singleton
service restart. The final active URL was:

```text
http://127.0.0.1:11490/.../blueprint-window/default
```

Verified in the in-app browser:

- The served bundle changed from the stale `index-B07CEF4s.js` to
  `index-DG7kuvhI.js`.
- The page shows `蓝图运行槽`, `启动蓝图运行槽`, and `发送到运行槽`.
- Old `直接运行`, old task input, and old plan-create selectors are absent.
- The start Agent control renders `agent-agent (agent)` after
  `runtime.start_node_id` is saved.
- The session dropdown opens from `会话 0`.
- The session dropdown shows the empty state, list container, `max-height:
  464px`, and `overflow-y: auto`.
- Clicking "启动蓝图运行槽" on the default blueprint shows the expected POPO entry
  error instead of `UNKNOWN_COMMAND`, and no live run is created.

The successful refreshed UI screenshot was saved at:

```text
.artifacts/blueprint-workbench-smoke-refreshed.png
```

The final error-state screenshot attempt timed out in CDP, so the final browser
evidence is the DOM smoke output plus service/API checks.

## Verification

Commands run:

```powershell
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build
```

Results:

- Typecheck passed.
- Frontend tests passed: `46 pass`, `902 expect() calls`.
- Production build passed with normal Vite large-chunk warnings and one existing
  JSX transform warning in `server-console-app.tsx`.
- Backend pytest passed separately: `84 passed, 1 skipped`.

## Notes

- If Workbench still shows the old UI after source changes, rebuild
  `GuLiCode/packages/app/dist`, reinstall the personal plugin mirror, then stop
  the old singleton service process before starting Workbench again.
- `stop_blueprint_workbench` stops the Workbench server, not necessarily the
  singleton service process. A stale singleton can continue serving old runtime
  code until killed or restarted.
