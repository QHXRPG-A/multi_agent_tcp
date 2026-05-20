# VCS-Style Workspace System Brainstorm

This document sketches a framework-owned workspace system for multi-agent code collaboration. The core idea is to stop treating the user project directory as the live write target for every agent. Instead, agents work in private checkouts and submit changesets back to the framework, while the framework performs conflict detection, merge, attribution, event emission, and final application.

## Problem

Direct multi-agent writes to a shared project directory are difficult to reason about:

- Two agents can edit the same file at the same time.
- A file lock can prevent simple same-path races, but it does not explain whether two changes are semantically mergeable.
- Codex CLI can be sandboxed as read-only, but then direct project writes are blocked and the framework needs a write path.
- OpenCode can be patched at the tool layer, but shell/plugin/custom tools still need policy boundaries.
- The runtime needs durable evidence for final reports: what each agent changed, what conflicted, what was accepted, and what was rejected.

The proposed direction is a small Git/SVN-like workspace broker controlled by `multi_agent_tcp`.

## Goal

Agents should interact with project code through a framework-owned lifecycle:

```text
project baseline
  -> framework checkout/sync
  -> agent private workspace
  -> agent edits privately
  -> agent submits changeset
  -> framework validates and merges
  -> accepted changes are applied to the project workdir
  -> events, reports, and archive records are emitted
```

The project workdir becomes an integration target owned by the runtime, not a shared scratchpad.

## Design Principles

- Agents can read broad project context, but write only in private workspaces unless explicitly allowed.
- The framework owns the authoritative project baseline and integration state.
- Agents submit changesets, not arbitrary filesystem side effects.
- Conflict detection should happen at submit time, not after silent overwrites.
- Conflict feedback must be structured enough for the agent to fix and resubmit.
- The first implementation can be file/diff based; later versions can use Dulwich commit/ref merge.
- The system must preserve provenance: agent id, task id, base ref, touched files, tests, conflicts, and final merge result.

## Main Concepts

### Project Baseline

A snapshot of the project at the start of a blueprint run, excluding framework directories such as `.multi_agent_workspace/`, `.git/`, caches, and generated dependency trees.

Initial implementation can use a copied directory snapshot. Later, if the project is a Git repo, use Dulwich object ids or tree ids as the baseline reference.

### Private Checkout

A per-agent writable workspace derived from the project baseline:

```text
.multi_agent_workspace/
  runs/active/<run_id>/
    base/
    agents/<agent_id>/
      private/
        checkout/
        state/
        codex_home/
        skills/
```

The agent edits `private/checkout/`. This directory is disposable run state, not the final output.

### Changeset

A submitted set of file changes relative to a known base ref.

At minimum:

```json
{
  "changeset_id": "cs_...",
  "run_id": "run_...",
  "agent_id": "agent_a",
  "task_id": "task_...",
  "base_ref": "base_...",
  "files": [
    {
      "path": "src/foo.py",
      "status": "modified",
      "base_hash": "...",
      "new_hash": "...",
      "patch": "..."
    }
  ],
  "summary": "...",
  "test_results": [],
  "risks": []
}
```

### Integration State

The runtime-maintained state of changes already accepted into the project workdir during the run.

This is distinct from the start baseline. A changeset may be based on the original run baseline but submitted after another agent has already changed the same file.

### Conflict

A structured submit result that tells the agent exactly why the changeset was not accepted and what context to use for repair.

Example:

```json
{
  "ok": false,
  "status": "conflict",
  "conflict_id": "cf_123",
  "files": [
    {
      "path": "src/foo.py",
      "reason": "stale_base",
      "base_version": 2,
      "current_version": 5,
      "agent_patch": "...",
      "current_patch": "...",
      "merge_preview": "<<<<<<< CURRENT\n...\n=======\n...\n>>>>>>> AGENT\n",
      "hint": "Both changes modify the same function body."
    }
  ]
}
```

## Proposed RPC/API Surface

The existing `workspace_rpc.py` can grow from publish-only shared outputs into a VCS-style API. Agents read project and current-run shared files directly from injected read-only filesystem paths; RPC remains the write/submit/publish control surface.

### `checkout`

Create or refresh an agent private checkout.

Input:

```json
{
  "command": "checkout",
  "args": {
    "scope": ["src/**", "tests/**"],
    "mode": "full"
  }
}
```

Output:

```json
{
  "ok": true,
  "checkout_id": "co_123",
  "base_ref": "base_abc",
  "checkout_path": "<agent-visible private path>",
  "writable": true
}
```

For both Codex and OpenCode strict mode, `checkout_path` is the only writable code workspace given to the agent. The real project directory should be mounted or exposed as read-only context.

### `status`

Return the diff between an agent checkout and its base.

Output:

```json
{
  "ok": true,
  "base_ref": "base_abc",
  "files": [
    {"path": "src/foo.py", "status": "modified", "additions": 12, "deletions": 4}
  ]
}
```

### `diff`

Return a patch for the private checkout.

Options should allow whole changeset, single file, or summary-only output to control token usage.

### `submit`

Submit a changeset for validation and integration.

Input can be either:

- a patch text,
- a manifest referencing files in the private checkout,
- or a framework-generated changeset id from `status`.

Output:

```json
{
  "ok": true,
  "status": "accepted",
  "changeset_id": "cs_123",
  "merged_files": ["src/foo.py"],
  "integration_ref": "int_456",
  "events": ["WorkspaceChanged", "ChangesetAccepted"]
}
```

or a conflict response as shown above.

### `sync`

Update an agent checkout with the latest accepted integration state.

This is useful after conflicts. It can either:

- replay accepted integration changes into the private checkout,
- or create a fresh checkout and ask the agent to reapply its patch.

### `resolve`

Submit a conflict resolution for a previous conflict id.

This can be implemented as `submit` with `conflict_id`, but an explicit command makes the flow easier for agents to understand.

### `commit_final`

At the end of a blueprint run, finalize accepted integration state into the user project workdir or long-term shared workspace.

For the first version, accepted changes can be applied immediately to the project workdir during each successful submit. A later version can stage them in `integration/` until the blueprint reaches auto-finish.

## Conflict Detection Strategy

MVP should handle reliable cases first:

1. Path outside allowed scope: reject.
2. Binary file changed by multiple parties: conflict.
3. File deleted by one side and modified by another: conflict.
4. Same file changed only by this agent since base: accept.
5. File changed by another agent, but edits are non-overlapping and text merge succeeds: accept with merge metadata.
6. Same region changed differently: conflict with merge preview.

The current `_merge_text(base, current, job)` in `workspace_manager.py` is a useful seed, but it is deliberately conservative. It should evolve into a file-oriented three-way merge that returns structured hunks.

## Token and Latency Considerations

The system should avoid making agents call RPC for every line edit.

Preferred flow:

- Agent reads project context from a read-only project tree or checkout.
- Agent edits freely in private checkout.
- Agent submits one patch set per task.
- Framework returns short structured status.
- Only conflicts return detailed patch context.

This keeps token growth bounded. Small changes add only a short submit response. Larger changes pay for patch text, which is already comparable to what direct edit tools expose in metadata.

For very large files or binary artifacts:

- submit by file reference inside the private checkout;
- return hashes and summaries instead of embedding full content;
- require human/super-agent review for high-risk binary replacement.

## Codex CLI Integration

Recommended strict mode:

```powershell
codex --ask-for-approval never exec `
  --sandbox read-only `
  --cd <project_root> `
  --output-last-message <agent_private_state>/last.txt `
  "<prompt>"
```

Then expose the framework workspace system through a runtime-owned tool or side channel.

Important caveat: if Codex runs a local CLI client inside the same read-only sandbox, that client may also be unable to write the project workdir. The authoritative writer should be the broker/runtime process outside the agent sandbox. The agent should submit patches or private-checkout references; the runtime applies them.

If the agent needs a writable checkout, launch Codex with:

- project root read-only as context;
- private checkout as the writable working directory;
- output/session files in agent private state.

The exact Windows sandbox behavior should be tested per launch shape.

## OpenCode Integration

To keep agent behavior consistent across CLI backends, OpenCode should follow the same workspace shape as Codex:

- the real project directory is read-only context;
- the agent's writable code surface is its private checkout;
- final project writes are performed only by the framework runtime after changeset submit and merge.

OpenCode is still easier to harden because its tool layer is source-editable:

- `read` can read from the read-only project context or the private checkout.
- `write`, `edit`, `multiedit`, and `apply_patch` should target the private checkout only.
- `submit` can be exposed as a first-class tool.
- `bash` must be disabled, restricted, or sandboxed so it cannot write the real project directory.
- custom/plugin tools must be disabled or given only framework-provided filesystem capabilities.

Tool-layer patching should enforce the same rule rather than introduce a separate OpenCode-only workflow. OpenCode may have richer internal hooks than Codex, but the agent-facing contract should remain: read project, edit checkout, submit changeset.

## Events

The VCS-style system should emit durable events:

- `CheckoutCreated`
- `CheckoutSynced`
- `FileChangedInCheckout`
- `ChangesetSubmitted`
- `ChangesetAccepted`
- `ConflictDetected`
- `ConflictResolved`
- `WorkspaceChanged`
- `ReviewRequested`
- `TaskCompleted`

Events should include `run_id`, `agent_id`, `task_id`, paths, versions, refs, and archive pointers.

## Archive Model

Each run archive should preserve:

```text
runs/archived/<run_id>/
  base/
  integration/
  changesets/
    cs_123/
      changeset.json
      patch.diff
      submit_result.json
  conflicts/
    cf_123/
      conflict.json
      resolution.diff
  reports/
    blueprint_result.json
    agent_reports/
```

Private checkouts can be discarded by default, because accepted/rejected changesets and conflict records are the durable history. Keep private checkouts only when debugging failed runs.

## Relationship to Workspace API

Current agent-facing API:

- `publish`
- `publish-file`
- `checkout`
- `status`
- `diff`
- `submit`
- `sync`

Current rules:

- `publish` and `publish-file` are only for run-scope reports/artifacts.
- Code changes use `checkout -> edit -> status/diff -> submit`.
- The run `shared/code` tree is an integration area owned by the framework, not a direct shared write surface.
- The long-term shared workspace is written by the framework as run archive zips. It is not exposed through Agent-facing read/list/archive commands.

## MVP Plan

### Phase 1: File Snapshot Changesets

- Add `checkout` to copy project baseline into `agents/<agent_id>/private/checkout`.
- Add `status` and `diff` from checkout to base.
- Add `submit` that validates scope and applies non-conflicting text changes to `integration/` or project workdir.
- Emit `ChangesetSubmitted`, `ChangesetAccepted`, and `ConflictDetected`.
- Archive changeset JSON and patch text.

### Phase 2: Conflict Repair Loop

- Return structured conflict records.
- Add `sync` to update private checkout against latest integration.
- Add `resolve` or `submit --conflict-id`.
- Add tests for stale base, same-file conflict, delete/modify, binary conflict, and clean non-overlap merge.

### Phase 3: Runtime Policy Integration

- Launch Codex with read-only project access and private writable checkout.
- Patch OpenCode tools to write only to private checkout.
- Disable or restrict bash/plugin bypasses in strict mode.
- Add final run report listing accepted, rejected, conflicted, and pending changesets.

### Phase 4: Dulwich Backend

- Represent baseline and integration refs as Git object refs when possible.
- Store changesets as commits or patch refs.
- Use Dulwich merge machinery where it is reliable.
- Keep file-based fallback for non-Git projects.

## Open Questions

- Should accepted changes apply immediately to the project workdir, or only at blueprint auto-finish?
- Should agents receive the real project root read-only plus private checkout, or only the private checkout?
- How should long-running tasks refresh their checkout without losing local work?
- Which paths require directory-level locks instead of file-level merge checks?
- Should formatting happen in the private checkout before submit, or in integration after merge?
- How much conflict context should be returned to avoid excessive tokens?
- How should human edits during a run enter the integration state?

## Recommended Direction

Use the VCS-style workspace system as the main concurrency model.

File leases are still useful for shared artifacts and short critical sections, but code collaboration should be changeset-based:

```text
private edit -> submit patchset -> framework merge -> conflict feedback -> resubmit
```

This gives the runtime a clean place to enforce policy, record provenance, support agent repair loops, and eventually swap the file-based backend for Dulwich/Git refs without changing the agent-facing contract.
