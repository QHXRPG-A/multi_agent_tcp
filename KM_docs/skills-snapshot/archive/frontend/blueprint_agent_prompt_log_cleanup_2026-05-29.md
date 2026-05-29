# Blueprint Agent Prompt and Log Cleanup - 2026-05-29

## Summary

This pass simplified the visible Blueprint Agent model in GuLiCode desktop and
split Agent description text from per-run prompt injection.

The user-visible Test Agent node entry was removed. Test Agent compatibility is
kept as an old add-kind alias, while new nodes are created and shown as normal
Agents. Agent information panel JSON snapshot logging is now controlled by a
global toolbar switch and remains enabled by default.

The Agent inspector now treats the old `prompt` field as the Agent description
(`简介`) and adds a new `run_prompt` field labeled `提示词`.

## Implemented

Blueprint model:

1. `test-agent` add-kind now delegates to normal Agent creation.
2. New Agent nodes no longer receive `gulicode_test_node`.
3. New Agent nodes include persistent `run_prompt: ""`.
4. Runtime graph export includes both `prompt` and `run_prompt`.
5. Start-plan creation continues to use `prompt` as Agent description and task
   fallback text. `run_prompt` is not used for planning descriptions.

Blueprint side panel:

1. Removed the Test Agent entry from the add-node menu.
2. Removed the Test Agent-specific title and yellow node styling branch.
3. Old `gulicode_test_node` markers no longer affect visible node appearance.
4. Added the toolbar switch `data-blueprint-test-log-toggle` backed by
   `Persist.global("blueprint-agent-panel-test-log.v1")`.
5. Snapshot persistence is gated by:
   - global test-log switch enabled
   - an Agent information panel with recordable state
   - `platform.saveBlueprintAgentPanelTest` being available
6. Turning the switch off clears pending snapshot timers and prevents new JSON
   writes.
7. Existing Electron IPC path, file names, schema, payload structure, and
   `createTestAgentPanelSnapshot` content remain unchanged.

Inspector copy:

1. The old Agent `提示词` textarea is now labeled `简介` and still binds to
   `prompt`.
2. A new `提示词` textarea binds to `run_prompt`.
3. Help text distinguishes description usage from per-run prompt injection.
4. English, Simplified Chinese, and Traditional Chinese strings were updated.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
3. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
4. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
5. `GuLiCode/packages/app/src/i18n/en.ts`
6. `GuLiCode/packages/app/src/i18n/zh.ts`
7. `GuLiCode/packages/app/src/i18n/zht.ts`

## Verification

Frontend:

```powershell
bun --cwd GuLiCode/packages/app test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
# pass

bun --cwd GuLiCode/packages/app typecheck
# pass
```

The existing `blueprint-test-agent-snapshot` content coverage remains in place
so JSON payload rules stay locked.

## Skill/Archive Files

Installed skill:

```text
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\frontend\blueprint_agent_prompt_log_cleanup_2026-05-29.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/frontend/blueprint_agent_prompt_log_cleanup_2026-05-29.md
```
