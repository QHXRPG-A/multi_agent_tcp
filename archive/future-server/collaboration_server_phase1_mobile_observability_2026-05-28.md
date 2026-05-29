# Collaboration Server Phase 1 + Mobile Observability

Date: 2026-05-28

## Summary

Implemented the first GuLiCode Collaboration Server as a FastAPI gateway and
connected the existing `/mobile` mock surface to same-origin read-only API
data. The server remains a gateway boundary: auth, project membership, admin
management, runtime binding, audit, safe projection, event replay/SSE, runtime
bridge reads, and disabled phase-2 write gates. It does not schedule
GraphRuntime, enqueue Agents, decide joins, or merge workspaces.

The same pass added operational observability for both server and mobile mock:
structured rotating server logs, runtime bridge request/success/failure logs,
SSE/event replay logs, mobile local ring-buffer logs, default mobile log upload
to `POST /api/client-logs`, sqlite `client_logs`, and admin-only
`GET /api/admin/logs/client`.

## Implemented Surface

- New Python package: `collaboration_server/`.
- CLI entry: `python -m multi_agent_tcp collaboration-server --host 127.0.0.1 --port 8787 --db logs/collaboration_server.sqlite3 --seed-config <path> --log-dir logs --log-level INFO`.
- Backend API includes auth, `/api/me`, projects, runs, run status, events,
  SSE stream, agent snapshot, diff, changeset diff, reports, artifacts, admin
  users/projects/members/runtime bindings, and client log ingestion/query.
- Mobile API client loads `/api/me -> /api/projects -> latest run -> status,
  diff, events`, preserving mock fallback and the existing three-tab UI.
- PWA sensitive paths stay `NetworkOnly`.

## Observability Contract

- Security audit remains in `audit_logs`.
- Operational server logs are JSONL records in rotating files.
- Mobile diagnostics are retained locally in a ring buffer and uploaded in
  capped batches to `client_logs`.
- Logging scrubs token/password/secret/cookie/csrf fields, local absolute
  paths, bridge token fields, and oversized payloads.

## Validation

- `pytest -q test_collaboration_server.py test_desktop_blueprint_service.py`
  passed: 46 passed, 1 skipped.
- `cd GuLiCode/packages/app && bun test --preload ./happydom.ts ./src/mobile ./src/pwa.ts`
  passed: 9 passed.
- `cd GuLiCode/packages/app && bun run typecheck` passed.
- `git diff --check` passed with only existing CRLF warnings.

## Follow-Up

- Add retention/pruning: `client_logs` default 30 days, audit logs retained
  longer or manually pruned, startup prune plus periodic 24h prune.
- Add admin/system diagnostics for log health and runtime bridge availability.
- Run manual same-origin smoke against a real desktop runtime binding.
- Keep phase-2 write endpoints gated until mobile send/approval/run-control
  permissions are explicitly designed.
