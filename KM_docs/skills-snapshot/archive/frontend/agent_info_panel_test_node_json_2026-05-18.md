# Agent Info Panel Test Node JSON Archive - 2026-05-18

## Scope

This records the GuLiCode blueprint Test Agent node pass for exercising the
Agent information panel and its JSON snapshot behavior.

## Current Behavior

- The Add Node menu includes a Test Agent preset for panel/runtime inspection.
- The special test-only right-click `Start test` action was removed. Test
  nodes should use the normal blueprint runtime start path.
- Test Agent panels persist a realtime JSON snapshot next to desktop logs.
- The Agent information panel displays the JSON path under `JSON location`.
- The JSON file is fixed, not timestamped:
  `%APPDATA%\ai.opencode.desktop.dev\logs\agent-info-panel-tests\agent-panel-test.json`.
- Desktop startup and `blueprint-start` clear the test JSON directory.
- Realtime panel persists overwrite the same file and remove obsolete
  timestamped `agent-panel-test-*.json` snapshots.
- User messages sent from the panel are recorded in `payload.userMessages`.
- User message status follows runtime lifecycle: `queued`, `sent`,
  `dispatching`, `running`, `succeeded`, `failed`.
- User messages store the runtime `message_id` as `runtimeMessageId` when
  available, plus timestamps and error fields.
- Runtime run-list status is merged from `status.run`, so snapshots do not
  contradict themselves after cancel, fail, or complete.
- Test Codex nodes set and backfill `skip_git_repo_check: true` to avoid the
  `C:\` trusted-directory smoke failure.

## JSON Shape

The saved file uses a wrapper plus a panel payload:

- `schema_version`
- `kind`
- `saved_at`
- `path`
- `payload.node`
- `payload.panel`
- `payload.userMessages`
- `payload.streamEvents`
- `payload.runtime`

The file is intended for live inspection, not as a durable historical event
log. A new desktop session or blueprint start resets it.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`

## Lessons And Pitfalls

- `sent` only means the IPC queue accepted a panel message. Worker success or
  failure must be derived from stream events or recent runtime events.
- Existing saved Test Agent nodes need normalization/backfill for
  `skip_git_repo_check`; only changing the new-node preset is insufficient.
- Do not create timestamped JSON files for realtime panel snapshots. Keep a
  single `agent-panel-test.json` and overwrite it.
- The earlier JSON parse issue came from tooling/encoding display around
  PowerShell, not from invalid persisted JSON.
- The `C:\` project directory smoke path can make Codex fail with
  `Not inside a trusted directory` unless the test node enables
  `skip_git_repo_check`.

## Latest Verification

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
bun run build
```

Latest debug restart reached:

- renderer: `http://localhost:5173/`
- sidecar: `http://127.0.0.1:9766`
- log: `GuLiCode/logs/gulicode-desktop-direct.log`

