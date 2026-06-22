# Blueprint File Send History Panel

Date: 2026-06-17

## Summary

This archive records the Workbench UI added for POPO file/image send records.

The Blueprint Control drawer now includes a separate panel under
`策划填表记录`:

```text
文件图片发送记录
```

The panel lists sessions that have POPO file/image send records. Clicking a
session opens a detail dialog with a table of individual sends.

Use this record when:

- `文件图片发送记录` is missing below `策划填表记录`
- the panel only appears after a hard refresh or plugin cache sync
- file/image history APIs exist but the Workbench does not call them
- the detail dialog is missing columns for time, type, status, file name, size,
  receiver, or path
- Codex cache still serves an old `web/dist` bundle after package refresh

## Main Files

- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/entry.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

## Platform API

The app platform now exposes:

```text
listBlueprintSessionFileSendHistory(projectDir, blueprintId)
blueprintSessionFileSendHistory(sessionKey, limit?)
```

`entry.tsx` maps them to:

```text
blueprint.sessions.fileSendHistoryList
blueprint.sessions.fileSendHistory
```

The API shape mirrors the existing Excel history API.

## Control Drawer UI

`BlueprintControlDrawer` renders the new panel immediately after:

```text
BlueprintExcelHistoryPanel
```

The file-send panel has stable test attributes:

```text
data-blueprint-file-send-history-panel
data-blueprint-file-send-history-list
data-blueprint-file-send-history-session
```

The panel shows:

- session display name
- session key
- latest send time
- latest message type
- latest status
- latest file name
- record count

When no records exist, the panel still renders with an empty state:

```text
当前蓝图暂无文件/图片发送记录
```

## Detail Dialog

Clicking a session opens `BlueprintFileSendHistoryDetailDialog`.

Stable attributes:

```text
data-blueprint-file-send-history-dialog
data-blueprint-file-send-history-table
data-blueprint-file-send-history-header
data-blueprint-file-send-history-record
```

Columns:

- time
- type
- status
- file name
- size
- receiver
- path

The display helpers cover:

- image vs ordinary file labels
- success and failure status labels
- compact path rendering
- byte/KB/MB/GB size formatting
- missing file names and zero-byte files

## I18n

Added keys under:

```text
blueprint.fileSendHistory.*
```

Locales updated:

- English
- Simplified Chinese
- Traditional Chinese

Chinese title:

```text
文件图片发送记录
```

Traditional Chinese title:

```text
檔案圖片發送記錄
```

## Codex Plugin Cache Gotcha

After the first implementation pass, the installed runtime and personal plugin
were updated, but the Codex app still displayed an old Workbench bundle. The
visible symptom was:

- `策划填表记录` appeared
- `文件图片发送记录` did not appear under it
- backend/runtime checks showed `blueprint_send_popo_file` was present

The cause was stale Codex plugin cache:

```text
C:\Users\qiuhaoxuan\.codex\plugins\cache\personal\gulicode-bp\0.1.3\web\dist
```

The personal plugin bundle was also checked:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\web\dist
```

The repo build output did contain the new panel:

```text
F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app\dist
```

Manual recovery used during this work:

1. Copy repo `GuLiCode/packages/app/dist` to:

   ```text
   C:\Users\qiuhaoxuan\plugins\gulicode-bp\web\dist
   ```

2. Copy the same dist to:

   ```text
   C:\Users\qiuhaoxuan\.codex\plugins\cache\personal\gulicode-bp\0.1.3\web\dist
   ```

3. Verify the bundles contain:

   ```text
   文件图片发送记录
   data-blueprint-file-send-history-panel
   fileSendHistory
   ```

4. Hard-refresh or reopen the Workbench tab.

When this panel is missing in a user screenshot, check the cache bundle before
debugging the component logic.

## Verification

Frontend test command:

```powershell
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts --timeout 120000
```

Result:

```text
36 pass
0 fail
1102 expect() calls
```

The production app build also completed successfully:

```powershell
bun run build
```

Relevant bundle checks after manual cache sync:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\web\dist\assets\*.js
C:\Users\qiuhaoxuan\.codex\plugins\cache\personal\gulicode-bp\0.1.3\web\dist\assets\*.js
```

Both contained the new file-send history panel markers.
