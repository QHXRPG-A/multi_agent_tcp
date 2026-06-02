# Blueprint Common Branch/Tick UI and Port Types - 2026-05-31

## Summary

This pass added framework-owned common Blueprint nodes to the GuLiCode canvas:
`Branch` and `Tick`.

Users can place these nodes from the node search, but they do not author script
definitions for them. The renderer also gained a shared port type model so
non-Agent and non-Script node connections are rejected before they are saved.

## Implemented

Common node model:

1. Added `common_nodes` to the frontend Blueprint graph draft.
2. Added `BlueprintCommonNode` with `kind: "branch"` and `kind: "tick"`.
3. Added `every_n_ticks` for Tick nodes, normalized to at least `1`.
4. Old Blueprint documents default `common_nodes` to `{}`.
5. Runtime graph serialization includes normalized `common_nodes`.

Node creation:

1. Right-click node search includes Branch and Tick options.
2. `addNode` delegates Branch/Tick creation to `addCommonNode`.
3. Branch nodes are selected and opened in the Inspector after placement.
4. Tick nodes expose `every_n_ticks` in the Inspector.

Canvas visual:

1. Branch shows `condition: bool`, `true: message`, and `false: message` labels
   beside its pins.
2. Branch input uses a triangle pin, matching Script Function Node inputs.
3. Branch is wider than a standard Agent/Route node so labels fit without
   overlapping the node title.
4. Tick remains compact and exposes a single `tick: tick` output.
5. Branch/Tick use common-node visual treatment distinct from Agent and Script
   nodes.

Port type validation:

1. Added `BlueprintPortDataType`: `message`, `bool`, and `tick`.
2. Added `canConnectPorts(draft, from, outputPort, to, inputPort)`.
3. `addEdge` refuses invalid non-Agent/non-Script type combinations.
4. Canvas drag-to-connect uses the same validation helper.
5. Inspector edge edits use the same validation helper.
6. Type mismatch and unknown-port failures show lightweight toast errors.
7. Agent and Script endpoints intentionally remain unchecked for this pass.

Start/run UI:

1. Direct run still requires selected start nodes unless the graph contains an
   enabled Tick source.
2. Tick-only direct run plans may have empty `start_nodes`.

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
cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Observed result during implementation:

```text
blueprint model + side panel focused suite: 44 passed
blueprint-side-panel focused suite after Branch pin-label tweak: 18 passed
app typecheck passed
```

Smoke check:

```text
Local Vite app available at http://127.0.0.1:5174
HTTP status: 200
```

## Known Limits

1. Script port type metadata is intentionally ignored by connection validation
   in this pass.
2. Agent ports are intentionally treated as untyped.
3. Branch condition input expects a strict runtime boolean; UI does not coerce
   strings such as `"true"` or `"false"`.

## Follow-Up Queue

1. Add interaction-level UI coverage for drag connection rejection once the
   test harness can drive Blueprint canvas pointer gestures reliably.
2. Revisit common node visual density after larger real Blueprints exist.
3. If Script Node typed-port compatibility becomes required, extend the shared
   `canConnectPorts` model instead of adding separate Script-specific checks.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\frontend\blueprint_common_nodes_branch_tick_ui_type_ports_2026-05-31.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/frontend/blueprint_common_nodes_branch_tick_ui_type_ports_2026-05-31.md
```
