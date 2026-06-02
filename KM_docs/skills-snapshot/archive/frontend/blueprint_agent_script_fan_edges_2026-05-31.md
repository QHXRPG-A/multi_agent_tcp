# Blueprint Agent Script Fan Edges - 2026-05-31

## Summary

This pass made Agent and Script Function Node wiring explicit in the Blueprint
canvas. Connecting an Agent to any input pin on a multi-input Script Node now
creates real sibling edges to every script input. Connecting any output pin from
a multi-output Script Node to an Agent now creates real sibling edges from every
script output to that Agent.

Single-input and single-output Script Nodes remain ordinary one-to-one
connections.

## Implemented

Model behavior:

1. `addEdge(...)` expands only the two supported Script/Agent patterns:
   Agent -> Script inputs and Script outputs -> Agent.
2. Fan expansion writes real `BlueprintEdge` records rather than a render-only
   projection.
3. Multi-input Script Nodes receive one edge per input port, preserving the
   original Agent output port.
4. Multi-output Script Nodes create one edge per output port, preserving the
   original Agent input port.
5. One-to-one Script Nodes keep the original single edge behavior.
6. `fanEdgeGroup(...)` groups siblings by shared Agent/Script endpoint and
   matching non-fanned port.
7. `deleteEdge(...)` deletes the full sibling group so half fan structures do
   not remain on the canvas.

Renderer behavior:

1. Visible edges are grouped before rendering.
2. Multi-edge Agent -> Script groups render as one source segment into a hub and
   then one segment per script input.
3. Multi-edge Script -> Agent groups render as one segment per script output
   into a hub and then one segment into the Agent.
4. Hub points are rendered with `data-blueprint-edge-fan-hub`.
5. Edge group containers are rendered with `data-blueprint-edge-group`.
6. Selecting any sibling highlights the full group.
7. Hovering any sibling highlights the full group.
8. Runtime flow dots still follow the concrete underlying edges so existing
   runtime edge ids keep working.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`

Tests:

1. `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Verification

Focused frontend tests:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Observed result:

```text
46 passed
app typecheck passed
```

Browser/manual smoke:

1. Started the local Vite app and opened the Blueprint window.
2. Confirmed edge group DOM renders for existing default edges.
3. Confirmed hub rendering is reserved for multi-edge fan groups.

## Follow-Up Queue

1. Add a pointer-level UI test that drags from a real Agent pin to a real Script
   pin once the harness can drive exact canvas coordinates reliably.
2. Consider exposing a subtle group-delete affordance in the Inspector if users
   need more discoverability than Delete/Backspace.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\frontend\blueprint_agent_script_fan_edges_2026-05-31.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/frontend/blueprint_agent_script_fan_edges_2026-05-31.md
```
