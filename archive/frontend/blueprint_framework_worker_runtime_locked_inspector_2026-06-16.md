# Blueprint Framework Worker Runtime Locked Inspector

Date: 2026-06-16

## Summary

This archive records the Workbench Inspector update that mirrors the runtime
split between Full Agent and Worker Agent framework instructions.

The Inspector no longer treats every Agent-class node as using
`framework-agent-runtime`. It now chooses locked framework skill/rule entries
by node type:

- Full Agent (`agent`) shows `framework-agent-runtime`
- Worker Agent (`worker_agent`) shows `framework-worker-runtime`
- Top Agent runtime selection remains outside this Inspector branch

Use this record when:

- a Worker Agent Inspector shows `framework-agent-runtime`
- a Full Agent Inspector shows worker workspace runtime entries
- locked framework skill/rule options are persisted into user-editable
  `skills` or `rule_paths`
- business skills disappear after adding locked framework runtime entries

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Behavior

The Inspector computes locked framework catalog items from the selected node's
type. The locked entries are visible, checked, disabled, and non-removable, but
they remain framework-owned UI/runtime references.

They are filtered out before persisting user-editable node fields:

```text
selectedAgent.skills
selectedAgent.rule_paths
selectedAgent.skill_selection.skill_hashes
```

User-selected business skills and business rule paths remain editable and are
stored as before.

## Frontend Test Coverage

The side-panel tests now assert that:

- Full Agent planner nodes use `framework-agent-runtime`
- ordinary Worker/Test/Observer nodes use `framework-worker-runtime`
- locked framework skill and rule entries are visible in the Inspector
- locked entries cannot be toggled off by user interaction
- locked framework entries are excluded from persisted user values

## Verification

Command run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
```

Result:

- 34 passed
- 0 failed
