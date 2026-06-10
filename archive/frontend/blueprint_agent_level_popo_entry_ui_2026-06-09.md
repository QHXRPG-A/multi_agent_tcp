# Blueprint Agent-Level POPO Entry UI

Date: 2026-06-09

## Summary

This archive records the Workbench UI changes for the agent-level POPO forwarding
model introduced by the 2026-06-09 POPO session refactor.

The UI now makes POPO forwarding a property of a full AgentNode instead of a
blueprint-level runtime setting. Only the saved start full Agent can enable POPO
forwarding, and only when no other full Agent has already enabled it.

## Graph Model

`BlueprintAgentNode` now has an optional `popo_entry` object with the POPO robot
configuration fields:

- `enabled`
- `robot_app_key`
- `robot_name`
- `robot_app_secret`
- `callback_token`
- `aes_key`

Model normalization keeps compatibility with legacy documents that stored POPO
configuration under `runtime.popo_entry`. When a saved start full Agent exists,
legacy config can be migrated into that AgentNode's `popo_entry`.

Runtime POPO defaults now save as an empty default structure so new documents do
not imply blueprint-level POPO ownership.

## Inspector Rules

The selected full Agent's Inspector owns the POPO forwarding controls.

Controls are editable only when:

- The selected node is a full AgentNode.
- The selected node is the saved start AgentNode.
- No other full AgentNode has `popo_entry.enabled = true`.

Controls are disabled with an adjacent reason when:

- The selected node is not the saved start AgentNode.
- Another full AgentNode already enabled POPO forwarding.
- The current selection is not a full AgentNode.

This matches the runtime rule that one Blueprint may have at most one
POPO-enabled full Agent, and that Agent must be the entry/start Agent.

When the saved start Agent changes, any POPO forwarding enabled on the previous
start Agent is cleared. This prevents the document from silently retaining an
invalid POPO entry after the user changes the start node.

## POPO Blueprint Indicator

When the saved start full Agent has POPO forwarding enabled, the Blueprint is
visually marked as a POPO Blueprint near the relevant start/POPO controls.

This is an indicator only. Runtime validation remains authoritative.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app`:

```powershell
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Results:

- Frontend tests passed: `52 pass`.
- Typecheck passed.

The personal plugin was rebuilt and restarted after the UI changes:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
.\start-gulicode-debug.ps1 -NoOpen -SkipPluginInstall
```

Workbench health and UI smoke:

- active blueprint-window URL returned 200.
- Headless page smoke rendered the Blueprint canvas and runtime panel.
- Screenshot saved to `logs\gulicode-bp-ui-smoke.png`.

The headless browser reported one non-blocking `401 Unauthorized` console warning
from the unauthenticated collaboration/login check. The Blueprint page itself
rendered successfully.
