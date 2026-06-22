# Blueprint Session Instance Runtime Panel

Date: 2026-06-11

## Summary

This archive records the Workbench/frontend companion work for the 2026-06-11
runtime change that removed Blueprint run slots.

The Workbench no longer presents a structure-level slot pool. The Runtime panel
is centered on the current Blueprint session:

- the user types a message into the current session
- the bridge calls `sendBlueprintSessionMessage`
- the backend creates or reuses the session's live run instance
- runtime status follows `activeRunId` for that session

There is no visible slot capacity, no pre-start slot action, and no terminate
slot button.

## Platform Bridge Changes

Removed platform methods:

```text
startBlueprintSlot
blueprintSlotStatus
terminateBlueprintSlot
sendBlueprintSlotMessage
```

Kept/used platform method:

```text
sendBlueprintSessionMessage(projectDir, blueprintId, message, input)
```

Electron IPC/preload/renderer wiring was updated to expose the session-message
bridge and remove the slot bridge methods.

## Runtime Panel Behavior

The Runtime panel message box now sends:

```text
source = "ui"
sessionKey = currentBlueprintSessionKey()
```

The panel derives the active run from the current session:

```text
currentBlueprintSession()?.activeRunId
```

The frontend tests assert that old slot bridge methods and old slot-capacity
helpers are absent from the source.

## Tests

Focused frontend verification:

```powershell
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts
```

Final result:

- 63 passed
- 0 failed

## Main Files

- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/entry.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`
