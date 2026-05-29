# GuLiCode Mobile PWA Mock First Pass

Date: 2026-05-27

Status: Superseded by `gulicode_mobile_top_tabs_mock_2026-05-28.md`.

## Scope

This archive records the first mock-only mobile PWA interface for GuLiCode. The
work stayed in the existing SolidJS/Vite app and did not call a server-side API.

## Implemented

- Added a `/mobile` entry that renders only the platform/app base providers and
  the mobile app surface.
- Kept `/mobile` out of `AppInterface`, `GlobalSDKProvider`, and
  `GlobalSyncProvider` so it can open without the desktop runtime stack.
- Added local mock data and pure mobile state transitions for projects, runs,
  events, tool cards, approvals, reports, pause/cancel/archive, and create-run.
- Added a mobile-first interface for project selection, run detail, event stream,
  tool cards, run list, create-run form, bottom actions, and reports.
- Integrated `vite-plugin-pwa` using `generateSW` and `autoUpdate`.
- Configured runtime-sensitive paths as `NetworkOnly`: `/auth/*`, `/api/*`,
  `/runs/*`, and `/stream`.
- Replaced placeholder public favicon/PWA assets with real GuLiCode icon assets.
- Added PWA registration and update/offline-ready UI events.
- Added focused unit and E2E coverage for the mobile mock workflow.

## Validation

Commands passed in `GuLiCode/packages/app`:

```powershell
bun run typecheck
bun test --preload ./happydom.ts ./src/mobile
bun run build
$env:PLAYWRIGHT_PORT='4310'; bun run test:e2e -- e2e/mobile.spec.ts
```

The production build generated:

- `dist/site.webmanifest`
- `dist/sw.js`
- `dist/workbox-2933a76c.js`

Browser verification confirmed the local `/mobile` page rendered, had no
horizontal overflow at the checked viewport, and kept the bottom navigation
visible.

## Superseded Items

The following first-pass concepts were later removed from the active mock:

- project selector
- run detail long cards
- tool cards
- event stream
- bottom navigation
- create run
- approval/archive actions
- report list

## Next Context

The next archived mock pass is the 2026-05-28 top-tabs version, which reframes
mobile as a read-only Top Agent conversation and blueprint status viewer.

