# Blueprint Multi Skill Rule Dirs Resident Drag

Date: 2026-06-10

## Summary

This archive records the Workbench frontend changes for multi-directory Skill
and Rule configuration, refreshed Inspector catalogs, Codex model fallback
updates, and draggable resident-service panel behavior.

Use this record when:

- global Blueprint config needs more than one Skill or Rule directory
- setting a Skill/Rule directory does not refresh Inspector dropdowns
- a currently selected Skill/Rule disappears after catalog refresh
- the resident-services floating panel cannot be moved
- model fallback options omit `gpt-5.5`

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/entry.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Config Model

`BlueprintConfig` now stores both plural and legacy fields:

```ts
skill_dir: string
skill_dirs: string[]
rule_dir: string
rule_dirs: string[]
```

Normalization rules:

- non-empty arrays win over legacy scalar fields
- old `skill_dir` / `rule_dir` migrate into one-item arrays
- persisted documents keep the plural arrays and also write the first effective
  path back to the legacy scalar fields

The default model remains `gpt-5.4`; only the model option catalog fallback now
includes `gpt-5.5`:

```ts
codex: ["gpt-5.5", "gpt-5.4"]
```

## Global Config UI

The Blueprint global config panel now includes both:

- Skill directory list
- Rule directory list

Each list supports:

- empty state text
- one-directory-at-a-time folder picker
- duplicate removal while preserving order
- row removal
- count / load-error status text

Changing a list updates both plural and legacy config fields. The catalog
refresh effect depends on `effectiveBlueprintSkillDirs` and
`effectiveBlueprintRuleDirs`, so Inspector Skills and Rule Paths refresh without
reloading the page.

The Inspector `MultiSelectField` already merges current selected values into
visible options, so a selected Skill or Rule that is no longer present in the
fresh catalog remains visible instead of being deleted silently.

## Workbench Bridge

`Platform.listBlueprintSkills` and `Platform.listBlueprintRules` accept:

```ts
string | string[] | undefined
```

The web bridge converts these into backend payloads:

- array -> `{ dirs: [...] }`
- non-empty string -> `{ dir: "..." }`
- empty/undefined -> `{}`

`entry.tsx` now wires:

- `blueprint.listSkills`
- `blueprint.listRules`
- `blueprint.listModels`

## Resident Services Panel

The resident-services floating panel is now positioned with local component
state instead of fixed `right/top` classes.

Behavior:

- initial position remains the visual top-right placement
- title bar has `data-blueprint-resident-drag-handle`
- pointer drag uses pointer capture
- drag events stop propagation and prevent canvas dragging
- position is clamped to the current viewport
- position is not persisted into the Blueprint document
- collapse/expand remains on the chevron control

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app`:

```powershell
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
```

Results:

- Typecheck passed.
- Frontend targeted tests passed: `61 pass`, `0 fail`.

Packaging/runtime smoke:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
```

Result:

- production web build completed
- personal plugin/cache updated
- singleton service restarted
- Workbench served at `http://127.0.0.1:5525/.../blueprint-window/fill-planning-form`
- runtime `/api/blueprint` accepted `blueprint.listRules`
