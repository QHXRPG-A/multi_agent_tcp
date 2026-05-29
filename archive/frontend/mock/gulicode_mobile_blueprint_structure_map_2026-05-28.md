# GuLiCode Mobile Blueprint Structure Map Mock

Date: 2026-05-28

## Scope

This archive records the `/mobile` Blueprint tab structure-map mock update. The
work remained frontend-only and did not add backend APIs, runtime controls,
blueprint editing, node dragging, or data-model changes.

## Implemented

- Added a top `Blueprint structure` preview area in the Blueprint tab before
  the existing blueprint title and summary sections.
- Kept the map as a read-only display of `mobileMockData.blueprint.nodes`.
- Added an in-app fullscreen overlay for the structure map with the existing
  close icon button.
- Replaced the percentage-based map with a fixed `980 x 560` logical canvas so
  node spacing is stable and the map is clipped instead of compressed on narrow
  mobile widths.
- Added viewport state for pan and zoom using
  `translate3d(x, y, 0) scale(zoom)`.
- Added mouse/touch dragging for panning and two-pointer pinch zoom.
- Added bottom-right zoom-in and zoom-out magnifier buttons.
- Changed nodes to opaque colored status cards and removed the previous black
  numbered node dot.
- Kept node spacing wide and allowed incomplete map visibility through viewport
  clipping.
- Reduced SVG arrow marker size from `14 x 14` to `3.5 x 3.5` after visual
  review, making arrowheads one quarter of the previous size.

## Files

- `GuLiCode/packages/app/src/mobile/mobile-app.tsx`
- `GuLiCode/packages/app/e2e/mobile.spec.ts`

## Validation

Full validation passed in `GuLiCode/packages/app` after the structure-map
refactor:

```powershell
bun run typecheck
bun test --preload ./happydom.ts ./src/mobile
bun run build
$env:PLAYWRIGHT_PORT='4310'; bun run test:e2e -- e2e/mobile.spec.ts
```

After the final arrow-size adjustment, these checks passed again:

```powershell
bun run typecheck
$env:PLAYWRIGHT_PORT='4310'; bun run test:e2e -- e2e/mobile.spec.ts
```

Browser verification at `http://127.0.0.1:4311/mobile` confirmed:

- structure-map preview renders at the top of the Blueprint tab
- nodes are opaque colored cards with no black number dot
- zoom buttons are visible and update the canvas transform
- fullscreen overlay opens and closes in-app
- SVG marker attributes are `markerWidth="3.5"` and `markerHeight="3.5"`
- no horizontal document overflow at the checked mobile viewport

## Guardrails

- Keep the mobile structure map read-only.
- Do not introduce node dragging, node editing, runtime start/stop, or approval
  actions in this mock.
- Keep map browsing as viewport pan/zoom only; do not resize or reflow the
  blueprint to fit the mobile card.
- Treat this archive as mock UI context, not a backend contract.
