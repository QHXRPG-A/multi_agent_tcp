# Agent Information Panel Markdown and Long-Press Update - 2026-05-20

## Scope

This pass covers the GuLiCode blueprint Agent information panel rendering and
open interaction refinements in:

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## User-Facing Behavior

1. Left mouse long-press on an Agent node now opens the Agent information panel
   after `500ms`.
2. The existing long-press cancellation behavior is unchanged: moving the
   pointer by `8px` or more cancels the pending open, as do pointer cancel,
   canvas interactions, port interactions, and panel move/resize interactions.
3. Agent reply rows render Markdown for `tone === "reply"` only.
4. User messages, reasoning rows, error rows, tool-call rows, and tool-call
   second-level expanded content remain plain text / `<pre>` for copyable
   debug output.
5. Tool-call grouping and individual tool-call second-level expansion are
   unchanged.

## Markdown Rendering Details

Agent reply bodies use the existing `@opencode-ai/ui/markdown` `Markdown`
component with the display event id as the cache key:

```tsx
<Markdown
  text={props.event.text}
  cacheKey={props.event.id}
  streaming={props.event.status !== "completed"}
  class={markdownClass}
/>
```

The Markdown branch is isolated in `AgentPanelDisplayEventBody`; its fallback
path keeps the previous plain-text `<pre>` rendering for every non-reply tone.

Panel-local compact styling keeps Markdown readable in the dark information
panel. Fenced code blocks are rendered as real code blocks, while `pre` and
Shiki `.shiki` backgrounds are forced to `#06101a` so generated code blocks do
not appear as bright white panels.

## Verification

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Observed result:

- `blueprint-side-panel.test.ts`: 9 passed
- app typecheck: passed

Browser smoke with Playwright was not rerun in this environment because the
Playwright Chromium binary was not installed locally.
