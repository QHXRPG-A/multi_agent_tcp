# Collaboration Server Mobile Write Loop

Date: 2026-05-28

## Summary

This pass upgraded the `/mobile` mock path from read-only API projection toward
a real Collaboration Server write loop. The server remains the security and
audit boundary: mobile writes go through session auth, CSRF, project role,
capability checks, audit records, payload scrubbing, and the desktop runtime
bridge.

The companion skill update added a `调试启动` workflow for launching the
Collaboration Server, GuLiCode desktop, and mock mobile `/mobile` client.

## Implemented

- Collaboration Server phase-2 write routes:
  - `POST /api/runs`
  - `POST /api/runs/{runId}/messages`
  - `POST /api/runs/{runId}/end`
  - `POST /api/runs/{runId}/approvals`
  - planning request routes under `/api/projects/{projectId}/planning-requests`
    and `/api/planning-requests/{id}/*`
- Runtime bridge forwarding for:
  - `blueprint.start`
  - `blueprint.queueAgentMessage`
  - `blueprint.end`
  - `blueprint.rollbackChangesets`
  - `blueprint.planning.markPlanStarted`
- Store schema extensions:
  - mobile-origin message records
  - approval records
  - planning requests and desktop state snapshots
- Role/capability expansion:
  - `owner` / `operator`: `run:create`, `run:message`, `run:end`,
    `run:approve`
  - `viewer`: read-only
- Mobile API client:
  - CSRF-aware POST helper with `credentials: "include"`
  - create planning request, send agent message, cancel run, approve diff,
    rollback diff, answer question, approve/reject plan
- Mobile UI:
  - Top Agent goal input for planning requests
  - Agent sheet message input and mode selector when API/capability ready
  - run cancel and start-planning entry points
  - diff approve and rollback controls
  - pending page for planning requests, questions, plan approval/rejection
  - mock/logged-out fallback remains read-only
- Desktop relay:
  - polls same-origin Collaboration Server for pending mobile planning requests
  - auto-submits goals into existing desktop blueprint planning with
    `[来自移动端]` prefix
  - syncs `pendingQuestion`, `pendingPlan`, and `activeRun` back to the server
  - forwards mobile question answers and plan rejection back into the desktop
    planning runtime
- Skill knowledge:
  - added `knowledge_base/debug_start.md`
  - registered `调试启动` in `SKILL.md`

## Validation

Passed:

```powershell
pytest -q test_collaboration_server.py test_desktop_blueprint_service.py
```

Result: `47 passed, 1 skipped`, with existing websocket deprecation warnings.

Passed:

```powershell
cd GuLiCode/packages/app
bun test --preload ./happydom.ts ./src/mobile ./src/pwa.ts
bun run typecheck
```

Result: mobile/PWA tests passed and TypeScript typecheck passed.

## Next Priority

Highest priority after this pass: front/backend integration testing
(`前后端联调测试`).

The next agent should use the `调试启动` workflow, then manually exercise the
real loop:

1. Start Collaboration Server, desktop, and `/mobile`.
2. Confirm auth/session/CSRF behavior.
3. Create a mobile planning request and verify desktop Top Agent planning sees
   `[来自移动端]`.
4. Verify pending question answer, pending plan approval, live run start, and
   `markPlanStarted`.
5. Send an agent message from mobile and verify runtime queue/audit behavior.
6. Approve diff and confirm it is audit-only.
7. Roll back an eligible terminal changeset and confirm runtime error handling
   on ineligible active runs.
8. Verify viewer/logged-out/fallback remain read-only.
9. Inspect audit/client logs for token, cookie, path, workspace, and MCP secret
   scrubbing.
