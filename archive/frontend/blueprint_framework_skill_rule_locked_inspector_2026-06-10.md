# Blueprint Framework Skill Rule Locked Inspector

Date: 2026-06-10

## Summary

This archive records the Workbench Inspector change that shows framework
skill/rule references as fixed selections on every Agent-class node.

The Inspector now displays the framework runtime skill and rule in the existing
Skills and Rule Paths fields for both full Agent and worker Agent nodes. These
items are visible and checked, but they are framework-owned and cannot be
removed by the user.

Use this record when:

- the Inspector shows no framework skill/rule on an Agent node
- a user can remove the framework skill/rule from the Agent Inspector
- a blueprint document unexpectedly persists framework items in `skills` or
  `rule_paths`
- adjusting `MultiSelectField` behavior for locked catalog items

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Behavior

The Inspector defines framework catalog items:

```text
framework-agent-runtime
framework_assets/rules/framework-agent-runtime.md
```

The selected Agent branch passes those items into `MultiSelectField` through
`lockedValues` and `lockedOptions` for the Skills and Rule Paths controls.

`MultiSelectField` now:

- merges locked values into the visible selected set
- renders locked items as checked and disabled
- ignores toggle attempts on locked values
- filters locked values out of editable values before calling `onChange`
- keeps user/business skill and rule options editable as before

The locked framework items are UI/runtime references only. They do not write
into `selectedAgent.skills`, `selectedAgent.rule_paths`, or
`skill_selection.skill_hashes`, and they do not require `rule_dir` to be set.

## Verification

Command run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
```

Result:

- `29 pass`
- `0 fail`

Additional check:

```powershell
git diff --check
```

Result:

- passed, with only CRLF normalization warnings.
