"""Per-agent private launch context materialization."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from .codex_bridge import validate_codex_launch_safety
from .graph_runtime import AgentNode
from .skill_space import SkillSpace
from .workspace_manager import DulwichWorkspaceManager, RunWorkspace
from .workspace_rpc import WorkspaceRPCServer


WORKSPACE_API_CONTEXT_ENV = "MULTI_AGENT_WORKSPACE_CONTEXT"
CODEX_RUNTIME_STATE_FILES = ("config.toml", "auth.json", "models_cache.json")


def is_framework_top_agent_node(node: AgentNode) -> bool:
    return str(node.node_id).startswith("top-agent-")


def workspace_api_base_command() -> str:
    python_exe = str(Path(sys.executable).expanduser())
    if os.name == "nt":
        quoted = subprocess.list2cmdline([python_exe])
        return f"& {quoted} -m multi_agent_tcp.workspace_api"
    quoted = shlex.quote(python_exe)
    return f"{quoted} -m multi_agent_tcp.workspace_api"


def _write_text_no_bom(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _default_user_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw and raw.strip():
        return Path(raw).expanduser()
    return Path.home() / ".codex"


def initialize_private_codex_home(
    codex_home: Path,
    *,
    source_codex_home: Optional[Path] = None,
) -> None:
    """Seed a private Codex home with runtime auth/config, not user skills."""

    codex_home.mkdir(parents=True, exist_ok=True)
    source = (source_codex_home or _default_user_codex_home()).expanduser()
    try:
        source = source.resolve()
        target = codex_home.resolve()
    except OSError:
        source = source.absolute()
        target = codex_home.absolute()
    if source == target:
        return

    copied_config = False
    for name in CODEX_RUNTIME_STATE_FILES:
        src = source / name
        if not src.is_file():
            continue
        dst = codex_home / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_config = copied_config or name == "config.toml"

    if not copied_config and not (codex_home / "config.toml").exists():
        _write_text_no_bom(codex_home / "config.toml", "")


def _safe_skill_dir_name(raw: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in raw)
    return safe.strip(".-") or "skill"


def _description_from_skill_md(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8-sig")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                stripped = line.strip()
                if stripped.startswith("description:"):
                    return stripped.split(":", 1)[1].strip().strip("\"'")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()
    return ""


def _resolve_agent_workdir(raw_cwd: Path, project_root: Path) -> Path:
    cwd = Path(raw_cwd).expanduser()
    if str(cwd).strip() in {"", "."}:
        cwd = project_root
    elif not cwd.is_absolute():
        cwd = project_root / cwd
    resolved = cwd.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"AgentNode cwd is not a directory: {resolved}")
    return resolved


def workspace_api_doc() -> str:
    command = workspace_api_base_command()
    doc_path = Path(__file__).with_name("docs") / "workspace_api.md"
    if not doc_path.is_file():
        return (
            f"Workspace API command: `{command}`. "
            "Use `checkout`, `status`, `diff`, `submit`, `publish-file`, "
            "and `publish`."
        )
    return doc_path.read_text(encoding="utf-8").replace(
        "python -m multi_agent_tcp.workspace_api",
        command,
    )


def framework_agent_rules() -> str:
    return "\n".join(
        [
            "# Multi-Agent Framework Baseline Rules",
            "",
            "- Understand the three workspace zones before acting: project directory is the authoritative code source/final target, private checkout is your personal workbench, temporary shared workspace is read-only collaboration state.",
            "- Read project_context / project_code_root directly as read-only context when you need project files.",
            "- Read the temporary shared workspace directly as read-only filesystem context when you need reports, artifacts, manifest.json, or logs.",
            "- Fetch or checkout only task-relevant code into your private checkout before editing.",
            "- Use framework MCP tools when they are configured in Codex.",
            "- Submit code changes from the private checkout through `workspace_submit`.",
            "- Publish reports, artifacts, summaries, file/version references, and changeset ids through `workspace_publish` / `workspace_publish_file`.",
            "- Do not write directly into project_context, project_code_root, or the temporary shared workspace as a code/output completion path.",
            "- If a direct project/shared write is denied by the sandbox, treat that as boundary enforcement and continue through checkout/submit/publish instead of stopping.",
            "- Communicate with other AgentNodes through framework messages and shared references, not by copying project source trees into shared space.",
            "- Your natural-language worker reply is a framework-private utterance record; it is not delivered to other AgentNodes.",
            "- To provide information to another AgentNode, use `agent_dispatch` for the current batch.",
            "- Sending an empty string `\"\"` or numeric `0` through `agent_dispatch` means this target has no task and should not receive a downstream message.",
            "- To provide durable results to the framework, use assigned framework MCP tools.",
            "- Do not request or depend on top-agent-only utterance inspection APIs.",
            "- Framework rules and skills are materialized once when your private worker context is prepared; per-message updates arrive only through `framework_context`.",
            "- Use only skills and rules exposed in your private CODEX_HOME/cwd context.",
        ]
    )


def framework_top_agent_rules() -> str:
    return "\n".join(
        [
            "# GuLiCode Desktop Top Agent Rules",
            "",
            "- You are operating inside GuLiCode desktop blueprint planning mode; the desktop app/current chat session is the Top Agent.",
            "- Do not assume, start, or ask for a separate bottom Top Agent CLI/worker.",
            "- Treat the desktop app as the authority for plan confirmation, runtime start, permissions, and audit.",
            "- Use only the injected `framework_control` MCP tools for organization, status, explanation, utterance inspection, user questions, and start-plan staging.",
            "- Ask missing blocking questions with `top_agent_request_user_input`; do not simulate user confirmation.",
            "- Validate a complete `TopAgentStartPlan` with `runtime_validate_start`, then stage it with `top_agent_stage_start_plan`.",
            "- Do not call `runtime_start`; the app calls `blueprint.start` only after the user approves the staged plan.",
            "- Do not modify, persist, or rewrite blueprint graph structure in v1.",
            "- Do not expose MCP tokens, private workspace paths, or framework internals to the user or ordinary agents.",
            "- Explain validation failures and runtime status directly and concisely.",
        ]
    )


def framework_agent_skill() -> str:
    return "\n".join(
        [
            "---",
            "name: framework-agent-runtime",
            "description: Baseline multi-agent runtime, MCP tools, dispatch, and private context workflow.",
            "---",
            "# Framework Agent Runtime",
            "",
            "Use the injected `framework_context` for your current message envelope, "
            "including `outgoing_batch_id`, required downstream targets, and `agent_dispatch` usage.",
            "The framework runtime skill is stable for the worker context; per-message state changes are provided through `framework_context`.",
            "",
            "If Codex lists a framework MCP server such as `framework_ordinary`, use those MCP tools first. "
            "They are the preferred interface for checkout/status/diff/submit/sync, publish/publish_file, and downstream dispatch. "
            "Read project files and temporary shared workspace files directly from the read-only paths injected into AGENTS.md, the prompt preamble, and the Codex Execution Context. "
            "The shared workspace includes reports, artifacts, manifest.json, and logs; write reports and artifacts through publish tools.",
            "",
            "Your final CLI reply is only a minimal framework-private utterance record "
            "containing who spoke, what was said, time, and task/message identity. "
            "It is not a communication channel to other AgentNodes and is not proof of submitted work.",
            "",
            "For code changes, edit the private checkout in the current working directory, "
            "fetching only task-relevant project files with `workspace_checkout`, "
            "inspect with `workspace_status` / `workspace_diff`, "
            "then submit through `workspace_submit`.",
            "If a direct write outside the private checkout is denied by sandbox policy, "
            "recover by using the framework checkout/submit flow rather than treating the denial as completed work.",
            "",
            "For reports and artifacts, publish through `workspace_publish` / `workspace_publish_file` "
            "as shared run context. Use summaries, file paths, versions, and changeset ids when another AgentNode needs code context. "
            "If you need a current shared path version, read the shared `manifest.json` file directly.",
            "",
            "For downstream messages, use the `agent_dispatch` MCP tool. The target must be listed in the current message's "
            "`framework_context.message_envelope.required_outgoing_targets`.",
            "If a target has no work, dispatch `\"\"` or `0` for that target; the framework records it as no-op and does not queue a downstream task.",
        ]
    )


def framework_top_agent_skill() -> str:
    return "\n".join(
        [
            "---",
            "name: framework-top-agent-runtime",
            "description: GuLiCode desktop Top Agent runtime-control planning workflow.",
            "---",
            "# GuLiCode Desktop Top Agent Runtime",
            "",
            "Use this skill when handling GuLiCode desktop blueprint planning mode. "
            "The desktop app/current chat session is the Top Agent; there is no separate bottom Top Agent CLI/worker. "
            "Your role is to understand the user's intent, inspect the current blueprint organization, ask any required questions, and stage a valid start plan for desktop confirmation.",
            "",
            "Workflow:",
            "- Inspect organization and status through `framework_control` before proposing a start plan.",
            "- If required choices or constraints are missing, call `top_agent_request_user_input(questions)` and wait for the desktop answer.",
            "- Build a complete `TopAgentStartPlan` with `user_goal`, `agent_descriptions`, `start_nodes`, `tasks`, and `run_policy`.",
            "- Call `runtime_validate_start(plan)` and fix validation errors before staging.",
            "- Call `top_agent_stage_start_plan(plan, plan_markdown)` when the proposal is ready for the user confirmation card.",
            "- After staging, summarize the plan and wait for the app/user confirmation flow.",
            "",
            "Boundaries:",
            "- Never call `runtime_start`; GuLiCode desktop starts the run after explicit approval.",
            "- Do not edit or save blueprint graph structure in v1.",
            "- Do not use ordinary worker workspace submit/publish APIs as a completion path.",
            "- Keep user-facing replies focused on questions, plan rationale, validation issues, and observed status.",
        ]
    )


def shared_workspace_context(run: RunWorkspace) -> Dict[str, Any]:
    return {
        "root": str(Path(run.shared_dir).resolve()),
        "reports": str(Path(run.shared_reports_dir).resolve()),
        "artifacts": str(Path(run.shared_artifacts_dir).resolve()),
        "manifest": str((Path(run.shared_dir) / "manifest.json").resolve()),
        "logs": str((Path(run.shared_dir) / "logs").resolve()),
        "readonly": True,
    }


def copy_skill_dir_to_codex_home(source_skill_dir: Path, codex_home: Path, *, name: Optional[str] = None) -> Dict[str, str]:
    source = Path(source_skill_dir).resolve()
    skill_md = source / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"skill directory missing SKILL.md: {source}")
    skill_name = _safe_skill_dir_name(name or source.name)
    target = codex_home / "skills" / skill_name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    copied_md = target / "SKILL.md"
    content = copied_md.read_text(encoding="utf-8-sig")
    _write_text_no_bom(copied_md, content)
    return {
        "name": skill_name,
        "description": _description_from_skill_md(copied_md),
        "skill_md_path": str(copied_md),
    }


def materialize_codex_skill_selection(
    node: AgentNode,
    *,
    codex_home: Path,
    skill_space: Optional[SkillSpace] = None,
) -> list[Dict[str, str]]:
    """Copy authorized business skills into the agent's private CODEX_HOME."""

    skills_root = codex_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    catalog: list[Dict[str, str]] = []

    is_top_agent = is_framework_top_agent_node(node)
    framework_name = "framework-top-agent-runtime" if is_top_agent else "framework-agent-runtime"
    framework_dir = skills_root / framework_name
    framework_dir.mkdir(parents=True, exist_ok=True)
    framework_md = framework_dir / "SKILL.md"
    _write_text_no_bom(
        framework_md,
        framework_top_agent_skill() if is_top_agent else framework_agent_skill(),
    )
    catalog.append(
        {
            "name": framework_name,
            "description": (
                "GuLiCode desktop Top Agent runtime-control planning workflow."
                if is_top_agent
                else "Baseline multi-agent runtime, MCP tools, dispatch, and private context workflow."
            ),
            "skill_md_path": str(framework_md),
            "source": "framework",
        }
    )

    if skill_space is None:
        return catalog
    hashes = node.resolve_skill_hashes(skill_space)
    for rec in skill_space.resolve_hashes(hashes):
        copied = copy_skill_dir_to_codex_home(
            rec.skill_dir,
            codex_home,
            name=f"{rec.skill_hash}-{rec.name}",
        )
        copied["hash"] = rec.skill_hash
        copied["source"] = "business"
        catalog.append(copied)
    return catalog


def materialize_rule_paths(
    rule_paths: Sequence[str],
    *,
    private_dir: Path,
    project_root: Path,
) -> list[Dict[str, str]]:
    rules_dir = private_dir / "rules"
    if rules_dir.exists():
        shutil.rmtree(rules_dir)
    rules_dir.mkdir(parents=True, exist_ok=True)
    catalog: list[Dict[str, str]] = []
    for index, raw in enumerate(rule_paths, start=1):
        source = Path(str(raw)).expanduser()
        if not source.is_absolute():
            source = project_root / source
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"rule file not found: {source}")
        target = rules_dir / f"{index:02d}-{_safe_skill_dir_name(source.stem)}{source.suffix or '.md'}"
        content = source.read_text(encoding="utf-8-sig")
        _write_text_no_bom(target, content)
        title = ""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("# ").strip()
                break
        catalog.append(
            {
                "name": title or source.stem,
                "description": f"Business rule copied from {source.name}",
                "rule_path": str(target),
            }
        )
    return catalog


def _build_prompt_execution_context(execution_context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a reduced execution context suitable for prompt injection."""
    prompt_context: Dict[str, Any] = {}

    code_workspace = execution_context.get("code_workspace")
    if isinstance(code_workspace, dict):
        prompt_code_workspace = {
            key: code_workspace[key]
            for key in (
                "project_context",
                "project_code_root",
                "checkout_path",
                "write_scope",
            )
            if key in code_workspace
        }
        if prompt_code_workspace:
            prompt_context["code_workspace"] = prompt_code_workspace

    shared_workspace = execution_context.get("shared_workspace")
    if isinstance(shared_workspace, dict):
        prompt_shared_workspace = {
            key: shared_workspace[key]
            for key in ("root", "reports", "artifacts", "manifest", "logs", "readonly")
            if key in shared_workspace
        }
        if prompt_shared_workspace:
            prompt_context["shared_workspace"] = prompt_shared_workspace

    private_context = execution_context.get("private_context")
    if isinstance(private_context, dict):
        prompt_private_context: Dict[str, Any] = {}
        skill_catalog = private_context.get("skill_catalog")
        if isinstance(skill_catalog, list):
            prompt_private_context["skill_catalog"] = [
                {
                    key: item[key]
                    for key in ("name", "description")
                    if isinstance(item, dict) and key in item
                }
                for item in skill_catalog
                if isinstance(item, dict)
            ]
        rule_catalog = private_context.get("rule_catalog")
        if isinstance(rule_catalog, list):
            prompt_private_context["rule_catalog"] = [
                {
                    key: item[key]
                    for key in ("name", "description")
                    if isinstance(item, dict) and key in item
                }
                for item in rule_catalog
                if isinstance(item, dict)
            ]
        if prompt_private_context:
            prompt_context["private_context"] = prompt_private_context

    workspace_scopes = execution_context.get("workspace_scopes")
    if workspace_scopes is not None:
        prompt_context["workspace_scopes"] = workspace_scopes

    mcp = execution_context.get("mcp")
    if isinstance(mcp, dict):
        prompt_mcp = {
            key: mcp[key]
            for key in ("enabled", "server_kind", "server_name", "tools")
            if key in mcp
        }
        if prompt_mcp:
            prompt_context["mcp"] = prompt_mcp

    return prompt_context


def _is_toml_bare_key(value: str) -> bool:
    return bool(value) and all(ch.isascii() and (ch.isalnum() or ch in {"_", "-"}) for ch in value)


def _remove_toml_table_block(text: str, table_name: str) -> str:
    header = f"[mcp_servers.{table_name}]"
    nested_prefix = f"[mcp_servers.{table_name}."
    lines = text.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if skipping and stripped.startswith("[") and stripped.endswith("]"):
            skipping = stripped == header or stripped.startswith(nested_prefix)
            if skipping:
                continue
        elif stripped == header or stripped.startswith(nested_prefix):
            skipping = True
            continue
        if not skipping:
            output.append(line)
    return "\n".join(output).rstrip() + ("\n" if output else "")


def write_private_codex_mcp_config(
    codex_home: Path,
    *,
    server_name: str,
    url: str,
    bearer_token_env_var: str,
    tools: Optional[Sequence[str]] = None,
    tool_approval_mode: str = "approve",
) -> None:
    server_key = str(server_name)
    if not _is_toml_bare_key(server_key):
        raise ValueError(f"Codex MCP server name is not a TOML bare key: {server_key!r}")
    tool_names = [str(item) for item in (tools or [])]
    for tool in tool_names:
        if not _is_toml_bare_key(tool):
            raise ValueError(f"Codex MCP tool name is not a TOML bare key: {tool!r}")
    config_path = codex_home / "config.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    existing = _remove_toml_table_block(existing, server_key)
    block_lines = [
        f"[mcp_servers.{server_key}]",
        "enabled = true",
        f"url = {json.dumps(str(url))}",
        f"bearer_token_env_var = {json.dumps(str(bearer_token_env_var))}",
    ]
    if tool_names:
        block_lines.append(f"enabled_tools = {json.dumps(tool_names)}")
    approval = str(tool_approval_mode or "").strip()
    if approval and tool_names:
        for tool in tool_names:
            block_lines.extend(
                [
                    "",
                    f"[mcp_servers.{server_key}.tools.{tool}]",
                    f"approval_mode = {json.dumps(approval)}",
                ]
            )
    block = "\n".join([*block_lines, ""])
    _write_text_no_bom(config_path, f"{existing.rstrip()}\n\n{block}" if existing.strip() else block)


def build_private_agents_md(
    *,
    node: AgentNode,
    project_context: Path,
    checkout_path: Path,
    shared_workspace: Dict[str, Any],
    business_rule_catalog: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    sections = [
        framework_top_agent_rules() if is_framework_top_agent_node(node) else framework_agent_rules(),
        "",
        "# Private Agent Workspace",
        "",
        f"- AgentNode: `{node.node_id}`",
        f"- Runtime agent id: `{node.runtime_agent_id}`",
        f"- Private checkout: `{checkout_path}`",
        f"- Read-only project context: `{project_context}`",
        f"- Read-only shared workspace: `{shared_workspace['root']}`",
        f"- Shared reports: `{shared_workspace['reports']}`",
        f"- Shared artifacts: `{shared_workspace['artifacts']}`",
        f"- Shared manifest: `{shared_workspace['manifest']}`",
        f"- Shared logs: `{shared_workspace['logs']}`",
        "",
        (
            "Use the control MCP for planning and status. Do not edit code or save blueprint graph structure from the Top Agent session."
            if is_framework_top_agent_node(node)
            else "Read project and shared files directly when you need context. Edit code only in the private checkout and submit it through the framework."
        ),
        "",
    ]
    if business_rule_catalog:
        sections.extend(
            [
                "# Business Rules",
                "",
                "The following business rule files are authorized for this agent. Read and follow them when relevant.",
                "",
            ]
        )
        for item in business_rule_catalog:
            sections.append(
                f"- `{item['name']}`: {item['description']} (file: `{item['rule_path']}`)"
            )
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def materialize_private_agent_context(
    node: AgentNode,
    *,
    manager: DulwichWorkspaceManager,
    run: RunWorkspace,
    rpc_server: WorkspaceRPCServer,
    skill_space: Optional[SkillSpace] = None,
    mcp_context_provider: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
) -> AgentNode:
    """Return an AgentNode rewritten to a private cwd/CODEX_HOME context."""

    workspace_api_command = workspace_api_base_command()
    project_context = _resolve_agent_workdir(node.cwd, manager.project_root)
    shared_workspace = shared_workspace_context(run)
    private_dir = manager.agent_workspace_dir(run, node.runtime_agent_id)
    checkout = manager.checkout_agent(run, node.runtime_agent_id, write_scope=node.write_scope)
    codex_home = private_dir / "codex_home"
    initialize_private_codex_home(codex_home)
    mcp_context: Optional[Dict[str, Any]] = None
    if mcp_context_provider is not None:
        candidate = mcp_context_provider(
            node=node,
            private_dir=private_dir,
            checkout_dir=checkout.checkout_dir,
            codex_home=codex_home,
        )
        if candidate:
            mcp_context = dict(candidate)
            write_private_codex_mcp_config(
                codex_home,
                server_name=str(mcp_context["server_name"]),
                url=str(mcp_context["url"]),
                bearer_token_env_var=str(mcp_context["bearer_token_env_var"]),
                tools=[str(item) for item in mcp_context.get("tools", [])],
            )

    skill_catalog = materialize_codex_skill_selection(
        node,
        codex_home=codex_home,
        skill_space=skill_space,
    )
    rule_catalog = materialize_rule_paths(
        node.rule_paths,
        private_dir=private_dir,
        project_root=manager.project_root,
    )
    agents_md = build_private_agents_md(
        node=node,
        project_context=project_context,
        checkout_path=checkout.checkout_dir,
        shared_workspace=shared_workspace,
        business_rule_catalog=rule_catalog,
    )
    _write_text_no_bom(checkout.checkout_dir / "AGENTS.md", agents_md)
    _write_text_no_bom(checkout.base_dir / "AGENTS.md", agents_md)

    api_context_path = private_dir / "workspace_api_context.json"
    _write_text_no_bom(
        api_context_path,
        json.dumps(rpc_server.context_for(node.runtime_agent_id), ensure_ascii=False, indent=2),
    )

    data = node.to_dict()
    data["cwd"] = str(checkout.checkout_dir)
    data["workspace_id"] = run.run_id
    data["read_scope"] = list(node.read_scope)
    data["write_scope"] = list(node.write_scope)
    data["artifact_scope"] = list(node.artifact_scope)

    if is_framework_top_agent_node(node):
        preamble = (
            "You are the GuLiCode desktop session Top Agent. "
            "Use the injected framework_control MCP for organization/status inspection, user questions, validation, and start-plan staging. "
            "Do not call runtime_start and do not edit or save blueprint graph structure; the desktop app starts runs only after user approval.\n\n"
            "Workspace paths are read-only context for planning:\n"
            f"- Read-only project_context: `{project_context}`\n"
            f"- Read-only project_code_root: `{manager.project_root}`\n"
            f"- Private checkout path: `{checkout.checkout_dir}`\n"
            f"- Read-only shared_workspace: `{shared_workspace['root']}`\n"
            f"- Shared reports: `{shared_workspace['reports']}`\n"
            f"- Shared artifacts: `{shared_workspace['artifacts']}`\n"
            f"- Shared manifest: `{shared_workspace['manifest']}`\n"
            f"- Shared logs: `{shared_workspace['logs']}`"
        )
    else:
        preamble = (
            "You are running inside a framework-managed three-zone workspace. "
            "The project directory is the authoritative code source and final code target; read it directly as read-only context, but do not edit it directly. "
            "Your private checkout is your personal workbench: fetch only the task-relevant code into it, edit there, and submit code changes as a changeset. "
            "The temporary shared workspace is read-only filesystem context for reports, artifacts, manifest.json, and logs; publish new reports and artifacts through the framework instead of writing shared files directly.\n\n"
            "Workspace paths:\n"
            f"- Read-only project_context: `{project_context}`\n"
            f"- Read-only project_code_root: `{manager.project_root}`\n"
            f"- Editable checkout_path: `{checkout.checkout_dir}`\n"
            f"- Read-only shared_workspace: `{shared_workspace['root']}`\n"
            f"- Shared reports: `{shared_workspace['reports']}`\n"
            f"- Shared artifacts: `{shared_workspace['artifacts']}`\n"
            f"- Shared manifest: `{shared_workspace['manifest']}`\n"
            f"- Shared logs: `{shared_workspace['logs']}`"
        )
    adapter_options = dict(data.get("adapter_options", {}))
    if node.cli_kind == "codex" and not adapter_options.get("sandbox"):
        adapter_options["sandbox"] = "workspace-write"
    if node.cli_kind == "codex":
        extra_args = adapter_options.get("extra_args", [])
        if not isinstance(extra_args, list) or not all(isinstance(x, str) for x in extra_args):
            raise ValueError("Codex AgentNode adapter_options.extra_args must be a list of strings")
        validate_codex_launch_safety(
            cwd=checkout.checkout_dir,
            sandbox=adapter_options.get("sandbox"),
            extra_args=[str(x) for x in extra_args],
            protected_readonly_roots=[
                project_context,
                manager.project_root,
                Path(shared_workspace["root"]),
            ],
        )
        adapter_options.setdefault("codex_home", str(codex_home))
        adapter_options.setdefault("diagnostics_dir", str(private_dir / "logs" / "codex"))
        adapter_options.setdefault("skip_git_repo_check", True)

    existing = adapter_options.get("prompt_preamble")
    if isinstance(existing, str) and existing.strip():
        adapter_options["prompt_preamble"] = f"{existing.strip()}\n\n{preamble}"
    else:
        adapter_options["prompt_preamble"] = preamble

    execution_context = dict(adapter_options.get("execution_context", {}))
    execution_context["workspace_api"] = {
        "command": workspace_api_command,
        "context_env": WORKSPACE_API_CONTEXT_ENV,
        "areas": ["artifacts", "reports"],
        "transport": "rpc",
        "rpc_url": rpc_server.url,
    }
    execution_context["code_workspace"] = {
        "mode": "vcs_checkout",
        "code_mode": manager._run_code_mode(run),
        "project_context": str(project_context),
        "integration_dir": str(run.integration_dir),
        "project_code_root": str(manager.project_root),
        "checkout_path": str(checkout.checkout_dir),
        "checkout_id": checkout.checkout_id,
        "base_ref": checkout.base_ref,
        "write_scope": list(checkout.write_scope),
        "submit_command": f"{workspace_api_command} submit",
    }
    execution_context["shared_workspace"] = dict(shared_workspace)
    execution_context["private_context"] = {
        "private_dir": str(private_dir),
        "codex_home": str(codex_home),
        "agents_md": str(checkout.checkout_dir / "AGENTS.md"),
        "skill_catalog": skill_catalog,
        "rule_catalog": rule_catalog,
    }
    execution_context["workspace_scopes"] = ["run"]
    if mcp_context is not None:
        execution_context["mcp"] = {
            "enabled": True,
            "server_kind": str(mcp_context.get("server_kind", "")),
            "server_name": str(mcp_context.get("server_name", "")),
            "tools": [str(item) for item in mcp_context.get("tools", [])],
        }
    adapter_options["execution_context"] = execution_context
    adapter_options["prompt_execution_context"] = _build_prompt_execution_context(execution_context)
    data["adapter_options"] = adapter_options

    extra_env = {str(k): str(v) for k, v in dict(data.get("extra_env", {})).items()}
    extra_env[WORKSPACE_API_CONTEXT_ENV] = str(api_context_path)
    if mcp_context is not None:
        extra_env[str(mcp_context["bearer_token_env_var"])] = str(mcp_context["bearer_token"])
    package_parent = str(Path(__file__).resolve().parent.parent)
    existing_pythonpath = extra_env.get("PYTHONPATH") or os.environ.get("PYTHONPATH")
    extra_env["PYTHONPATH"] = (
        f"{package_parent}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else package_parent
    )
    data["extra_env"] = extra_env
    return AgentNode.from_dict(data)
