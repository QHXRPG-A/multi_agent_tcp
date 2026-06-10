"""Per-agent private launch context materialization."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from .codex_bridge import validate_codex_launch_safety
from .graph_runtime import AgentNode
from .skill_space import SkillSpace
from .workspace_manager import DulwichWorkspaceManager, RunWorkspace
from .workspace_rpc import WorkspaceRPCServer


WORKSPACE_API_CONTEXT_ENV = "MULTI_AGENT_WORKSPACE_CONTEXT"
CODEX_RUNTIME_STATE_FILES = ("config.toml", "auth.json", "models_cache.json")
LOCAL_MCP_NO_PROXY_HOSTS = ("127.0.0.1", "localhost", "::1")
CODEX_DANGEROUS_BYPASS_ARG = "--dangerously-bypass-approvals-and-sandbox"
FRAMEWORK_ASSETS_DIR = Path(__file__).resolve().parent / "framework_assets"
FRAMEWORK_AGENT_RUNTIME_NAME = "framework-agent-runtime"
FRAMEWORK_TOP_AGENT_RUNTIME_NAME = "framework-top-agent-runtime"
PROXY_ENV_NAMES_BY_SCHEME = {
    "http": ("HTTP_PROXY", "http_proxy"),
    "https": ("HTTPS_PROXY", "https_proxy"),
    "ftp": ("FTP_PROXY", "ftp_proxy"),
    "all": ("ALL_PROXY", "all_proxy"),
}


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


def _split_no_proxy_hosts(raw: str) -> list[str]:
    return str(raw).replace(";", ",").split(",")


def _merge_no_proxy_hosts(existing: Sequence[str] | str, hosts: Sequence[str]) -> str:
    seen: set[str] = set()
    merged: list[str] = []
    values = [existing] if isinstance(existing, str) else list(existing)
    parts: list[str] = []
    for value in values:
        parts.extend(_split_no_proxy_hosts(str(value)))
    for item in [*parts, *hosts]:
        value = str(item).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return ",".join(merged)


def _apply_local_mcp_proxy_env(extra_env: Dict[str, str]) -> None:
    system_proxies = urllib.request.getproxies()
    no_proxy = _merge_no_proxy_hosts(
        [
            extra_env.get("NO_PROXY", ""),
            extra_env.get("no_proxy", ""),
            os.environ.get("NO_PROXY", ""),
            os.environ.get("no_proxy", ""),
            system_proxies.get("no", ""),
        ],
        LOCAL_MCP_NO_PROXY_HOSTS,
    )
    extra_env["NO_PROXY"] = no_proxy
    extra_env["no_proxy"] = no_proxy

    for scheme, names in PROXY_ENV_NAMES_BY_SCHEME.items():
        value = next((extra_env[name] for name in names if extra_env.get(name)), None)
        if value is None:
            value = next((os.environ[name] for name in names if os.environ.get(name)), None)
        if value is None:
            value = system_proxies.get(scheme)
        if not value:
            continue
        for name in names:
            extra_env.setdefault(name, str(value))


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


def _framework_runtime_name(*, is_top_agent: bool) -> str:
    return FRAMEWORK_TOP_AGENT_RUNTIME_NAME if is_top_agent else FRAMEWORK_AGENT_RUNTIME_NAME


def _framework_skill_dir(*, is_top_agent: bool) -> Path:
    return FRAMEWORK_ASSETS_DIR / "skills" / _framework_runtime_name(is_top_agent=is_top_agent)


def _framework_rule_path(*, is_top_agent: bool) -> Path:
    return FRAMEWORK_ASSETS_DIR / "rules" / f"{_framework_runtime_name(is_top_agent=is_top_agent)}.md"


def _read_framework_asset(path: Path) -> str:
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"framework asset not found: {resolved}")
    return resolved.read_text(encoding="utf-8")


def framework_agent_rules() -> str:
    return _read_framework_asset(_framework_rule_path(is_top_agent=False))


def framework_top_agent_rules() -> str:
    return _read_framework_asset(_framework_rule_path(is_top_agent=True))


def framework_agent_skill() -> str:
    return _read_framework_asset(_framework_skill_dir(is_top_agent=False) / "SKILL.md")


def framework_top_agent_skill() -> str:
    return _read_framework_asset(_framework_skill_dir(is_top_agent=True) / "SKILL.md")


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


def materialize_framework_skill(node: AgentNode, *, codex_home: Path) -> Dict[str, str]:
    is_top_agent = is_framework_top_agent_node(node)
    framework_name = _framework_runtime_name(is_top_agent=is_top_agent)
    copied = copy_skill_dir_to_codex_home(
        _framework_skill_dir(is_top_agent=is_top_agent),
        codex_home,
        name=framework_name,
    )
    copied["source"] = "framework"
    return copied


def materialize_codex_skill_selection(
    node: AgentNode,
    *,
    codex_home: Path,
    skill_space: Optional[SkillSpace] = None,
) -> list[Dict[str, str]]:
    """Copy authorized business skills into the agent's private CODEX_HOME."""

    skills_root = codex_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    catalog: list[Dict[str, str]] = [materialize_framework_skill(node, codex_home=codex_home)]

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


def _markdown_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()
    return ""


def materialize_framework_rule(node: AgentNode, *, private_dir: Path) -> Dict[str, str]:
    is_top_agent = is_framework_top_agent_node(node)
    framework_name = _framework_runtime_name(is_top_agent=is_top_agent)
    source = _framework_rule_path(is_top_agent=is_top_agent)
    content = source.read_text(encoding="utf-8")
    rules_dir = private_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / f"{framework_name}.md"
    _write_text_no_bom(target, content)
    return {
        "name": framework_name,
        "description": _markdown_title(content) or f"Framework rule copied from {source.name}",
        "rule_path": str(target),
        "source": "framework",
    }


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
        title = _markdown_title(content)
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
    rule_catalog: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    sections = [
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

    framework_rules = [
        item
        for item in (rule_catalog or [])
        if isinstance(item, dict) and item.get("source") == "framework"
    ]
    business_rules = [
        item
        for item in (rule_catalog or [])
        if isinstance(item, dict) and item.get("source") != "framework"
    ]
    if framework_rules:
        sections.extend(
            [
                "# Framework Rules",
                "",
                "The following framework rule files are required for this agent. Read and follow them before acting.",
                "",
            ]
        )
        for item in framework_rules:
            sections.append(
                f"- `{item['name']}`: {item['description']} (file: `{item['rule_path']}`)"
            )
        sections.append("")
    if business_rules:
        sections.extend(
            [
                "# Business Rules",
                "",
                "The following business rule files are authorized for this agent. Read and follow them when relevant.",
                "",
            ]
        )
        for item in business_rules:
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
    business_rule_catalog = materialize_rule_paths(
        node.rule_paths,
        private_dir=private_dir,
        project_root=manager.project_root,
    )
    framework_rule = materialize_framework_rule(node, private_dir=private_dir)
    rule_catalog = [framework_rule, *business_rule_catalog]
    agents_md = build_private_agents_md(
        node=node,
        project_context=project_context,
        checkout_path=checkout.checkout_dir,
        shared_workspace=shared_workspace,
        rule_catalog=rule_catalog,
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
        _apply_local_mcp_proxy_env(extra_env)
    package_parent = str(Path(__file__).resolve().parent.parent)
    existing_pythonpath = extra_env.get("PYTHONPATH") or os.environ.get("PYTHONPATH")
    extra_env["PYTHONPATH"] = (
        f"{package_parent}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else package_parent
    )
    data["extra_env"] = extra_env
    return AgentNode.from_dict(data)


def materialize_full_agent_context(
    node: AgentNode,
    *,
    project_root: Optional[Path] = None,
    run: Optional[RunWorkspace] = None,
    mcp_context_provider: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
) -> AgentNode:
    """Return a full CLI AgentNode with optional message-only MCP wiring.

    Unlike private worker materialization, this does not create a checkout or
    rewrite the agent into the framework workspace. The only files created are
    runtime support files for Codex MCP configuration and diagnostics.
    """

    root = Path(project_root).expanduser() if project_root is not None else Path(node.cwd).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    cwd = _resolve_agent_workdir(node.cwd, root)
    support_root = (
        Path(getattr(run, "path")) / "runtime_agent_context"
        if run is not None and getattr(run, "path", None) is not None
        else Path(tempfile.gettempdir()) / "multi_agent_tcp_full_agent_context"
    )
    support_dir = support_root / _safe_skill_dir_name(node.runtime_agent_id)
    support_dir.mkdir(parents=True, exist_ok=True)

    data = node.to_dict()
    data["cwd"] = str(cwd)
    data.pop("workspace_id", None)
    data.pop("workspace_root", None)
    data["read_scope"] = []
    data["write_scope"] = []
    data["artifact_scope"] = []

    adapter_options = dict(data.get("adapter_options", {}))
    access_policy = dict(getattr(node, "access_policy", {}) or {})
    mcp_context: Optional[Dict[str, Any]] = None
    codex_home = support_dir / "codex_home"
    skill_catalog: list[Dict[str, str]] = []
    rule_catalog: list[Dict[str, str]] = []
    if node.cli_kind == "codex":
        initialize_private_codex_home(codex_home)
        skill_catalog = [materialize_framework_skill(node, codex_home=codex_home)]
        materialize_rule_paths([], private_dir=support_dir, project_root=root)
        rule_catalog = [materialize_framework_rule(node, private_dir=support_dir)]
        adapter_options.setdefault("codex_home", str(codex_home))
        adapter_options.setdefault("diagnostics_dir", str(support_dir / "logs" / "codex"))
        adapter_options.setdefault("skip_git_repo_check", True)
        if bool(access_policy.get("disable_sandbox", True)):
            adapter_options["sandbox"] = "danger-full-access"
            adapter_options["dangerous_access"] = True
            extra_args = adapter_options.get("extra_args", [])
            if not isinstance(extra_args, list) or not all(isinstance(x, str) for x in extra_args):
                raise ValueError("Codex AgentNode adapter_options.extra_args must be a list of strings")
            if CODEX_DANGEROUS_BYPASS_ARG not in extra_args:
                extra_args = [*extra_args, CODEX_DANGEROUS_BYPASS_ARG]
            adapter_options["extra_args"] = [str(item) for item in extra_args]
        else:
            adapter_options["dangerous_access"] = False
            adapter_options["sandbox"] = (
                "workspace-write"
                if bool(access_policy.get("direct_project_io", True))
                else "read-only"
            )
            extra_args = adapter_options.get("extra_args", [])
            if isinstance(extra_args, list):
                adapter_options["extra_args"] = [
                    str(item)
                    for item in extra_args
                    if str(item) != CODEX_DANGEROUS_BYPASS_ARG
                ]

        if bool(access_policy.get("framework_message_tools", True)) and mcp_context_provider is not None:
            candidate = mcp_context_provider(
                node=node,
                private_dir=support_dir,
                checkout_dir=cwd,
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

    execution_context = dict(adapter_options.get("execution_context", {}))
    execution_context["agent_access"] = {
        "node_type": "agent",
        "project_workdir": str(cwd),
        "direct_project_io": bool(access_policy.get("direct_project_io", True)),
        "outside_project_io": bool(access_policy.get("outside_project_io", True)),
        "unrestricted_commands": bool(access_policy.get("unrestricted_commands", True)),
        "disable_sandbox": bool(access_policy.get("disable_sandbox", True)),
        "blueprint_monitor_tools": bool(access_policy.get("blueprint_monitor_tools", False)),
        "workspace_tools": False,
    }
    if mcp_context is not None:
        execution_context["mcp"] = {
            "enabled": True,
            "server_kind": str(mcp_context.get("server_kind", "")),
            "server_name": str(mcp_context.get("server_name", "")),
            "tools": [str(item) for item in mcp_context.get("tools", [])],
        }
    if skill_catalog or rule_catalog:
        execution_context["private_context"] = {
            "support_dir": str(support_dir),
            "codex_home": str(codex_home),
            "skill_catalog": skill_catalog,
            "rule_catalog": rule_catalog,
        }
        framework_lines = [
            "Framework runtime assets are materialized for this Agent:",
            *[
                f"- Skill `{item['name']}`: {item['description']} (file: `{item['skill_md_path']}`)"
                for item in skill_catalog
            ],
            *[
                f"- Rule `{item['name']}`: {item['description']} (file: `{item['rule_path']}`)"
                for item in rule_catalog
            ],
            "Read and follow the framework rule file before acting.",
        ]
        framework_preamble = "\n".join(framework_lines)
        existing = adapter_options.get("prompt_preamble")
        if isinstance(existing, str) and existing.strip():
            adapter_options["prompt_preamble"] = f"{existing.strip()}\n\n{framework_preamble}"
        else:
            adapter_options["prompt_preamble"] = framework_preamble
    adapter_options["execution_context"] = execution_context
    adapter_options["prompt_execution_context"] = _build_prompt_execution_context(execution_context)
    data["adapter_options"] = adapter_options

    extra_env = {str(k): str(v) for k, v in dict(data.get("extra_env", {})).items()}
    if mcp_context is not None:
        extra_env[str(mcp_context["bearer_token_env_var"])] = str(mcp_context["bearer_token"])
        _apply_local_mcp_proxy_env(extra_env)
    data["extra_env"] = extra_env
    return AgentNode.from_dict(data)
