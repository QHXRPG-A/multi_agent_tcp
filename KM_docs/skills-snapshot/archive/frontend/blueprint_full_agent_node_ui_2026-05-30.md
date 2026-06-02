# Blueprint Full Agent Node UI - 2026-05-30

## Summary

This pass split the user-visible Blueprint Agent node into two node types:

1. `Agent`: a full CLI node intended to run directly in the project working
   directory with broad access.
2. `Worker Agent`: the renamed original framework-managed Agent with private
   checkout and workspace-tool semantics unchanged.

The new full `Agent` node is visually distinct in the Blueprint canvas and side
panel. It uses an opaque light-green treatment so users can tell it apart from
framework-managed Worker Agents.

## Implemented

Blueprint model:

1. Added `node_type` normalization for `agent` and `worker_agent`.
2. Added `access_policy` defaults for full `Agent` nodes.
3. Migrated old blueprint documents without `node_type` to `worker_agent`.
4. Marked built-in/default blueprint nodes as `worker_agent`.

Node creation and inspector:

1. The add-node menu now exposes both `Agent` and `Worker Agent`.
2. New full `Agent` nodes default to `cli_kind="codex"` and all access-policy
   switches enabled.
3. The full `Agent` inspector shows permission switches:
   `direct_project_io`, `outside_project_io`, `unrestricted_commands`,
   `disable_sandbox`, and `framework_message_tools`.
4. `Worker Agent` keeps the existing inspector surface and does not expose the
   framework-managed cwd/workspace/scope fields as normal user controls.

Visual design:

1. Full `Agent` nodes now use an opaque light-green background:
   `linear-gradient(135deg, #bbf7d0, #86efac)`.
2. Full `Agent` node border/icon/text colors were adjusted for contrast on the
   opaque green surface.
3. Existing Worker Agent styling remains separate from the full Agent styling.

I18n:

1. Updated English, Simplified Chinese, and Traditional Chinese labels so the
   original Agent is presented as `Worker Agent`.
2. Added help text for the new full-Agent access-policy switches.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
3. `GuLiCode/packages/app/src/i18n/en.ts`
4. `GuLiCode/packages/app/src/i18n/zh.ts`
5. `GuLiCode/packages/app/src/i18n/zht.ts`

Tests:

1. `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Verification

Renderer focused tests:

```powershell
bun --cwd GuLiCode/packages/app test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
```

Observed result:

```text
384 passed
```

The focused tests cover node defaults, old blueprint migration to
`worker_agent`, add-menu labels, conditional inspector rendering, and the
opaque green full-Agent node tone.

## Follow-Up Queue

1. Run a manual GuLiCode visual smoke with mixed `Agent` and `Worker Agent`
   nodes at desktop and narrow panel widths.
2. If product copy changes, keep the visible names aligned with JSON
   `node_type` values: `Agent` maps to `agent`, `Worker Agent` maps to
   `worker_agent`.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\frontend\blueprint_full_agent_node_ui_2026-05-30.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/frontend/blueprint_full_agent_node_ui_2026-05-30.md
```
