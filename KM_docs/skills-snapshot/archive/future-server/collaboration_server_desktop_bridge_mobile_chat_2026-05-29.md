# Collaboration Server Desktop Bridge Mobile Chat

Date: 2026-05-29

## Summary

This pass moved `/mobile` from a mostly planning-focused write loop to a real
account-level desktop-control surface. A mobile client can now use the
Collaboration Server to send chat or blueprint-planning requests to the single
active desktop session for the same account. The desktop bridge forwards those
requests into the Electron renderer so behavior is equivalent to selecting a
desktop PromptInput mode and clicking submit.

The server remains the trust boundary. It stores session mirrors and forwards
commands, but it does not own PromptInput behavior, desktop session creation, or
runtime scheduling.

## Implemented

- Account/session model:
  - Multiple `mobile` sessions may stay active for the same account.
  - Only one active `desktop` session is allowed per account; a new desktop
    login takes over the old desktop session.
  - Desktop bridge registration is bound to the active desktop auth session, so
    revoked desktop sessions cannot keep registering bridges or uploading
    session snapshots.
- Desktop control bridge:
  - Electron main exposes a loopback-only desktop control bridge with a random
    token.
  - Desktop login registers `{ bridgeUrl, bridgeToken }` through
    `POST /api/desktop/bridge`.
  - Mobile writes call Collaboration Server endpoints first; the server then
    invokes desktop bridge commands:
    - `desktop.mobilePlanning.submit`
    - `desktop.session.submit`
    - `desktop.session.delete`
  - Renderer bridge handling dispatches into existing desktop submit paths.
- Desktop session mirror:
  - `POST /api/desktop/session-snapshot` stores account-level session summaries,
    active session id, current message details, structured message segments, and
    composer mode mirror.
  - Snapshot dependency tracking includes current message part text/tool/status
    revisions, so assistant replies are re-uploaded after streaming parts arrive
    instead of getting stuck as `[assistant message]`.
  - Snapshot payloads are scrubbed and do not expose cookie, CSRF, bridge token,
    raw IP, or runtime secret values.
- Mobile desktop sessions API:
  - `GET /api/mobile/desktop-sessions` returns desktop online/logged-in/stale
    status, session summaries, current messages, and composer modes.
  - `/api/mobile/tick` also includes the same desktop session mirror.
  - Tick projection prioritizes desktop chat messages over blueprint placeholder
    messages even when no live blueprint run/status exists.
- Mobile submit protocol:
  - `POST /api/mobile/desktop-submit` accepts `promptMode:
    "normal" | "blueprintPlanning"` and optional `agentName`.
  - The old `mode: "default" | "top"` remains accepted for compatibility but the
    mobile UI no longer sends `default/top` for desktop chat.
  - Desktop submit handling validates requested agent names; missing agents
    return `AGENT_NOT_FOUND`.
  - `blueprintPlanning` mode goes through the existing desktop blueprint
    planning submit path.
- Mobile chat UI:
  - The chat tab is localized as `聊天`.
  - Chat card fills the tab's available area; message history scrolls inside
    the card and the send form remains fixed at the bottom of the card.
  - Session chips, clear button, current messages, mode selector, and send form
    live in one integrated chat box.
  - Mode selector mirrors the desktop PromptInput selector: dynamic agent modes
    such as `build`/`plan` plus `蓝图规划`; it shows `等待桌面模式` until desktop
    snapshot modes arrive.
  - `清空` deletes the current desktop session through the desktop bridge, matching
    desktop session deletion semantics.
- Structured mobile message rendering:
  - Desktop snapshots preserve message `segments`.
  - Text segments render as Markdown.
  - Reasoning and tool segments render as compact disclosure rows, default
    collapsed.
  - Tool/reasoning cards preserve expanded state across mobile ticks using a
    stable `messageId:type:segmentId` key.
  - Expanded tool/reasoning cards lock to their collapsed width and scroll
    internally, so long input/output text does not widen the chat bubble.
  - User interaction with disclosures pauses auto-stick-to-bottom; tick no
    longer jumps the chat scrollbar while the user is inspecting expanded
    details.
- Mobile density/settings:
  - The mobile settings dropdown is opaque.
  - `gulicode.mobile.font-size` localStorage setting supports `小 / 标准 / 大`.
  - Small mode tightens mobile page density, card padding, form spacing, and
    compact segment sizing.
- Server console and debug startup:
  - `/console` runs on the GuLiCode app dev server as a read-only admin
    Collaboration Server console.
  - `GET /api/admin/monitor/users` exposes redacted user/session/client
    monitoring.
  - Debug startup was updated to open `/mobile` and `/console` with the
    Collaboration Server and desktop.

## Important Fixes From Live Debug

- The initial mobile send worked on desktop but did not appear on mobile because
  tick projection replaced desktop chat messages with the
  `Default Blueprint is unknown` placeholder whenever no blueprint run/status
  existed. The fix makes desktop session messages take precedence.
- Assistant replies initially appeared as `[assistant message]` because the
  desktop snapshot uploaded before assistant text parts streamed in and did not
  reschedule after part changes. The fix tracks message part revision keys and
  resubmits snapshots when text/tool/reasoning content changes.
- Reasoning/tool disclosures closed on every tick because open state lived
  inside per-segment components. The fix lifts state to `TopAgentPanel` and keys
  it by stable segment identity.
- Expanded tool cards widened and the chat scrollbar jumped because long
  preformatted content affected layout and tick-triggered DOM replacement
  interacted with scroll anchoring. The fix locks expanded width, adds internal
  overflow, uses stable list rendering, and disables auto-stick while inspecting
  details.

## Public Interfaces

- `POST /api/desktop/bridge`
- `POST /api/desktop/session-snapshot`
- `GET /api/mobile/desktop-sessions`
- `POST /api/mobile/desktop-submit`
- `POST /api/mobile/desktop-session-delete`
- `GET /api/admin/monitor/users`
- Desktop bridge commands:
  - `desktop.mobilePlanning.submit`
  - `desktop.session.submit`
  - `desktop.session.delete`

## Validation

Passed during implementation:

```powershell
python -m pytest -q test_collaboration_server.py
```

Result: `18 passed`.

```powershell
cd GuLiCode/packages/app
bun test --preload ./happydom.ts ./src/mobile ./src/components/collaboration-auth.test.ts ./src/pages/session/blueprint-planning-session.test.ts
bun run typecheck
```

Result: mobile/collaboration tests passed and TypeScript typecheck passed.

```powershell
cd GuLiCode/packages/desktop-electron
bun run typecheck
```

Result: desktop Electron typecheck passed.

Live smoke evidence:

- `/mobile` logged in with `1 / 1`.
- Mobile `您好` submitted through Collaboration Server to desktop.
- Desktop created/used the active session and replied.
- `/api/mobile/desktop-sessions` returned the user message plus assistant text
  and structured reasoning/text segments.
- Mobile chat rendered both messages.
- Expanded `思考过程` stayed open across ticks.
- Expanded disclosure width stayed constant and scrollTop remained stable across
  ticks during manual inspection.

## Next Priority

1. Add a browser-level regression test for the live disclosure behavior:
   expanded reasoning/tool row stays open, width-stable, and scroll-stable while
   `/api/mobile/tick` refreshes.
2. Decide whether mobile should expose a visible desktop-session selector when
   multiple desktop session summaries exist, or keep following the desktop
   active session only.
3. Add stale/online UI treatment for cases where desktop is logged in but the
   bridge or session snapshot has gone stale.
4. Promote the desktop bridge transport to SSE/WebSocket or another reverse
   channel before any non-local deployment; the current loopback request path is
   only appropriate for local debug/LAN assumptions.
