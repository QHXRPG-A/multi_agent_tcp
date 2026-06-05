# Blueprint Resident Services Panel Search, Pagination, and Collapse

Date: 2026-06-05

## Scope

Polished the Workbench resident services panel after the global resident service
feature landed. This was a frontend-only follow-up for the plugin-served
Blueprint workbench; backend resident service control commands and runtime
behavior were not changed.

## Panel Behavior

- Added local search state for the resident services panel.
- Search filters the loaded service list by `service_name`, `title`, and
  `description`, case-insensitively.
- Search changes reset the current resident services page to page 1.
- Empty search results show the dedicated no-match copy instead of reusing the
  no-service empty state.
- Fixed the no-match condition so an empty catalog with a search query still
  reports no matches rather than "no resident services".

## Pagination

- Added `RESIDENT_SERVICE_PAGE_SIZE = 5`.
- The panel renders only the filtered current page, with at most five resident
  services per page.
- Added first, previous, next, and last page controls:
  `<<`, `<`, `>`, and `>>`.
- Boundary controls are disabled on the first or last page.
- The page indicator uses the localized `current / total` format.
- Page state is clamped when service refreshes or search filtering reduce the
  total page count.
- The create-service button remains at the bottom; pagination sits above it.

## Collapse and Refresh

- The panel header now toggles visual collapse through
  `residentServiceCollapsed`.
- The header exposes `data-blueprint-resident-toggle` and
  `aria-expanded={!residentServiceCollapsed()}` for tests and accessibility.
- Collapsed state hides search, list, pagination, and create controls, while
  keeping the title bar visible.
- The former close-looking top-right button was replaced with a chevron toggle.
- Refresh is a separate header action and no longer doubles as the collapse
  affordance.
- Collapse state is purely local UI state and is not persisted to the blueprint
  document or backend.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

## Test Coverage

Updated `blueprint-side-panel.test.ts` to assert:

- `RESIDENT_SERVICE_PAGE_SIZE = 5`
- local state names for search, page, and collapsed status
- search input test selector
- pagination container and four pagination button selectors
- title-bar toggle selector and `aria-expanded` binding
- the resident service no-match i18n key
- no regression to the old `services().length > 0` no-match condition

Updated i18n with:

- `blueprint.resident.searchPlaceholder`
- `blueprint.resident.noMatches`
- `blueprint.resident.pageStatus`
- `blueprint.resident.firstPage`
- `blueprint.resident.previousPage`
- `blueprint.resident.nextPage`
- `blueprint.resident.lastPage`
- `blueprint.resident.expand`
- `blueprint.resident.collapse`

## Verification

Commands run from `GuLiCode/packages/app`:

```powershell
bun test src/pages/session/blueprint-side-panel.test.ts src/i18n/parity.test.ts
bun run typecheck
```

Repository check:

```powershell
git diff --check
```

Packaging and install:

```powershell
.\package-gulicode-bp-plugin.cmd -NoSmoke
```

Workbench smoke:

- Restarted the plugin workbench after packaging.
- Opened
  `http://127.0.0.1:14357/.../blueprint-window/default`.
- Verified the panel renders search, pagination, and the collapse toggle.
- Verified collapsing hides search and pagination while leaving the title bar.
- Verified searching for `no-such-resident-service` displays the no-match copy
  and does not display the generic no-service empty state.
- Verified `blueprint.residentServices` returns normally through MCP.

## Notes

- The resident services panel still refreshes independently of Tick nodes; the
  earlier red error flash was stabilized separately.
- Existing Vite chunk/import warnings and pip temporary-distribution warnings
  were observed during packaging and were not part of this UI change.
- The Workbench page must be reopened or reloaded against the newly started
  plugin URL after packaging; already-open old URLs continue serving their old
  bundle.
