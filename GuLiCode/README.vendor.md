# GuLiCode

GuLiCode is a rebuildable, runnable baseline copied from the upstream OpenCode workspace and intended for gradual integration into `multi_agent_tcp`.

Upstream:
- Repository: https://github.com/anomalyco/opencode
- License: MIT
- Local source baseline: `multi_agent_tcp/opencode/`

Rebuild policy:
- Keep workspace/package structure required for Bun startup
- Exclude generated dependencies and local build caches such as `node_modules`, `dist`, `.next`, `.turbo`, `.sst`, and `.git`
- Preserve upstream license and core workspace metadata so the baseline remains runnable

Important:
- This directory is meant to stay bootable first, then be trimmed incrementally with repeated startup verification.
- If `GuLiCode` is mentioned publicly, clarify that it is an independent project derived from OpenCode and is not affiliated with the OpenCode team.
