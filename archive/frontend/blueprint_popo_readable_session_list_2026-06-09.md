# Blueprint POPO Readable Session List

Date: 2026-06-09

## Summary

This archive records the Workbench UI companion change for readable POPO
Blueprint session identities.

The backend now returns POPO private session keys that include the POPO user
label, for example:

```text
bps_popo_qiuhaoxuan-corp.netease.com_1c718047678a3180a07553de
```

The session list keeps the session key visible as the primary monospaced line,
so users can confirm that the conversation belongs to the expected POPO user.
The second line uses `sessionDisplayName` when available, for example:

```text
POPO qiuhaoxuan@corp.netease.com
```

If `sessionDisplayName` is not present, the UI falls back to the Blueprint name,
then Blueprint id, then the unknown-blueprint localized text.

## UI Contract

`BlueprintSessionSummary` now has:

```ts
sessionDisplayName?: string
```

The dropdown card display rules are:

- First line: always `session.sessionKey`.
- Tooltip/title on the first line: also `session.sessionKey`.
- Second line: `sessionDisplayName || blueprintName || blueprintId || unknown`.
- Delete behavior still uses `session.sessionKey`.

This keeps the underlying session identity visible and leaves the stable delete
key unchanged.

## Main Files

- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python -m pytest test_desktop_blueprint_service.py -q -k "popo_private_session_key or legacy_hash_session_key or popo_slot_message_without_project_dir"
```

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app`:

```powershell
bun run typecheck
```

Results:

- Focused readable-session tests passed: `3 passed, 110 deselected`.
- Frontend typecheck passed.

The personal plugin was rebuilt and the runtime restarted. The installed
frontend bundle was checked to contain the new session display logic:

```text
sessionDisplayName || blueprintName || blueprintId || unknownBlueprint
```

The active Workbench after restart was:

```text
http://127.0.0.1:14467/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default
```

