# Workspace API CLI and RPC Contract

This CLI/RPC contract is kept for framework internals, tests, and debugging. In normal live Codex runs, ordinary Agents should use the configured MCP tools and direct read-only filesystem paths; the CLI command set is not injected into the Agent prompt-facing context.

Blueprint agents work with three workspace zones:

- `project_context` / `project_code_root`: authoritative code source and final code target. Agents may read these paths directly, but must not edit them directly.
- `checkout_path`: the writable private code workbench. The worker process starts with this path as `cwd`.
- `shared_workspace`: the current run's temporary shared workspace. Agents may read this physical directory directly, including `reports`, `artifacts`, `manifest.json`, and `logs`; agents publish new shared outputs through framework tools instead of writing files there directly.

The framework injects these paths into `AGENTS.md`, the prompt preamble, and the Codex Execution Context before the agent starts.

Code changes use a VCS-style private checkout. In project-reference mode, accepted submissions merge back to the project directory; in legacy snapshot mode, they merge into the run integration tree. Run-scope reports and artifacts use `publish` / `publish-file`; run-scope code never does.

For Codex workers, the blueprint runtime defaults to `codex exec --sandbox workspace-write --cd <checkout_path>` unless the node explicitly overrides the Codex sandbox option. Strict launch validation rejects `danger-full-access` and rejects `--add-dir` entries that would make the project or shared workspace roots writable.

## Command

```powershell
python -m multi_agent_tcp.workspace_api <command> [options]
```

The command is a thin client over the run-owned local RPC endpoint when `MULTI_AGENT_WORKSPACE_CONTEXT` points at an RPC context.

## Areas

- `artifacts`: generated images, documents, binary-adjacent text metadata, or other reusable assets.
- `reports`: summaries, manifests, test results, review notes, and structured run outputs.

## VCS-Style Code Flow

Create or refresh the agent checkout:

```powershell
python -m multi_agent_tcp.workspace_api checkout --path "src/parser.py" --path "tests/test_parser.py"
```

or:

```powershell
python -m multi_agent_tcp.workspace_api checkout --scope-path "src/**" --scope-path "tests/**"
```

The command returns JSON with `checkout_path`, `checkout_id`, `base_ref`, and `writable`. Edit files under `checkout_path`. Prefer explicit `--path` entries for focused tasks; use broad `--scope-path` only when the task truly needs that whole area.

Inspect checkout changes:

```powershell
python -m multi_agent_tcp.workspace_api status
python -m multi_agent_tcp.workspace_api diff
python -m multi_agent_tcp.workspace_api diff --summary
```

Submit the checkout as a changeset:

```powershell
python -m multi_agent_tcp.workspace_api submit --task-id task-123 --summary "Implement parser fix"
```

Accepted submissions are merged into the current code target and archived under `changesets/<changeset_id>/`. Conflicts return `ok: false`, `status: "conflict"`, and structured file entries with `reason`, hashes, and a merge preview when available. After a conflict, refresh from the latest code target:

```powershell
python -m multi_agent_tcp.workspace_api sync
```

Then reapply the fix in the private checkout and submit again.

## Publish Text

Write UTF-8 text to a specific outcome area. The framework acquires a file lease, writes atomically, records the write in the shared manifest, then releases the lease.

```powershell
"summary" | python -m multi_agent_tcp.workspace_api publish --area reports --path result.md --stdin
```

```powershell
python -m multi_agent_tcp.workspace_api publish --area reports --path status.json --text "{\"ok\": true}"
```

The command prints JSON with `ok`, `area`, `path`, `owner`, and `version`. It does not print a new physical path because the shared root is already injected into the agent context.

For version-checked publish workflows, read `shared_workspace.manifest` directly to find the current path version, then pass it to publish. Cross-agent overwrites of an existing shared path require `--expected-version`; without it the command fails instead of silently replacing another agent's output.

```powershell
python -m multi_agent_tcp.workspace_api publish --area reports --path result.md --file updated.md --expected-version 3
```

If another agent published the same path after the observed version, the command fails with a version conflict instead of overwriting newer content.

## Publish File

Publish any local file, including images and other binary artifacts. The file is copied through the framework API under a lease.

```powershell
python -m multi_agent_tcp.workspace_api publish-file --area artifacts --path images/result.png --file local_result.png
```

The command prints JSON with `ok`, `area`, `path`, `owner`, `bytes`, and `version`.

`publish-file` also supports `--expected-version <N>` for version-checked workflows.

## Rules

- Read project files directly from `project_context` / `project_code_root`.
- Read run-shared reports, artifacts, manifest, and logs directly from `shared_workspace`.
- Treat the project directory and shared workspace as read-only completion targets.
- Make code edits only in `checkout_path`.
- Code collaboration must use `checkout -> edit -> status/diff -> submit`.
- Use `publish-file --area artifacts` for generated assets such as images or binary files.
- Use `publish --area reports` for summaries, manifests, and test output.
- Keep private scratch files private. Only data published through the API is treated as a run outcome.
- If a publish command reports a lock or version conflict, stop and report the conflict instead of overwriting the file.

Agent-facing `read`, `list`, `list-archives`, and `extract-archive` Workspace API commands are intentionally not exposed. Internal manager read/archive methods remain available to the framework for reports, archiving, tests, and state projection.
