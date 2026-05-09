"""Per-agent private launch context materialization."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .codex_bridge import validate_codex_launch_safety
from .graph_runtime import AgentNode
from .skill_space import SkillSpace
from .workspace_manager import DulwichWorkspaceManager, RunWorkspace
from .workspace_rpc import WorkspaceRPCServer


WORKSPACE_API_CONTEXT_ENV = "MULTI_AGENT_WORKSPACE_CONTEXT"


def _write_text_no_bom(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
    doc_path = Path(__file__).with_name("docs") / "workspace_api.md"
    if not doc_path.is_file():
        return (
            "Workspace API command: `python -m multi_agent_tcp.workspace_api`. "
            "Use `checkout`, `status`, `diff`, `submit`, `publish-file`, "
            "`publish`, `read`, `list`, `list-archives`, and `extract-archive`."
        )
    return doc_path.read_text(encoding="utf-8")


def framework_agent_rules() -> str:
    return "\n".join(
        [
            "# Multi-Agent Framework Baseline Rules",
            "",
            "- Work only inside your private working directory unless a framework API says otherwise.",
            "- Treat the real project directory and long-term workspace as read-only context.",
            "- Do not write project changes directly outside the private checkout.",
            "- Submit code changes through `python -m multi_agent_tcp.workspace_api submit`.",
            "- Publish reports and artifacts through the Workspace API.",
            "- Communicate with other AgentNodes only through framework messages and shared references.",
            "- Your natural-language worker reply is a framework-private utterance record; it is not delivered to other AgentNodes.",
            "- To provide information to another AgentNode, use the injected `agent.dispatch` interface for the current batch.",
            "- To provide durable results to the framework, use Workspace API submit/publish or an assigned structured framework tool.",
            "- Do not request or depend on top-agent-only utterance inspection APIs.",
            "- Use only skills and rules exposed in your private CODEX_HOME/cwd context.",
        ]
    )


def framework_agent_skill() -> str:
    return "\n".join(
        [
            "---",
            "name: framework-agent-runtime",
            "description: Baseline multi-agent runtime, workspace API, dispatch, and private context workflow.",
            "---",
            "# Framework Agent Runtime",
            "",
            "Use the injected `framework_context` for your current message envelope, "
            "including `outgoing_batch_id`, required downstream targets, and `agent.dispatch` usage.",
            "",
            "Your final CLI reply is only a minimal framework-private utterance record "
            "containing who spoke, what was said, time, and task/message identity. "
            "It is not a communication channel to other AgentNodes and is not proof of submitted work.",
            "",
            "For code changes, edit the private checkout in the current working directory, "
            "inspect with `python -m multi_agent_tcp.workspace_api status` or `diff`, "
            "then submit through `python -m multi_agent_tcp.workspace_api submit`.",
            "",
            "For reports and artifacts, publish through `python -m multi_agent_tcp.workspace_api` "
            "instead of writing into shared workspace paths directly.",
        ]
    )


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

    framework_dir = skills_root / "framework-agent-runtime"
    framework_dir.mkdir(parents=True, exist_ok=True)
    framework_md = framework_dir / "SKILL.md"
    _write_text_no_bom(framework_md, framework_agent_skill())
    catalog.append(
        {
            "name": "framework-agent-runtime",
            "description": "Baseline multi-agent runtime, workspace API, dispatch, and private context workflow.",
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


def build_private_agents_md(
    *,
    node: AgentNode,
    project_context: Path,
    checkout_path: Path,
    business_rule_catalog: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    sections = [
        framework_agent_rules(),
        "",
        "# Private Agent Workspace",
        "",
        f"- AgentNode: `{node.node_id}`",
        f"- Runtime agent id: `{node.runtime_agent_id}`",
        f"- Private checkout: `{checkout_path}`",
        f"- Read-only project context: `{project_context}`",
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
) -> AgentNode:
    """Return an AgentNode rewritten to a private cwd/CODEX_HOME context."""

    project_context = _resolve_agent_workdir(node.cwd, manager.project_root)
    private_dir = manager.agent_workspace_dir(run, node.runtime_agent_id)
    checkout = manager.checkout_agent(run, node.runtime_agent_id, write_scope=node.write_scope)
    codex_home = private_dir / "codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)
    _write_text_no_bom(codex_home / "config.toml", "")

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
        business_rule_catalog=rule_catalog,
    )
    _write_text_no_bom(checkout.checkout_dir / "AGENTS.md", agents_md)

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

    preamble = (
        "You are running inside a framework-managed private Agent workspace. "
        "The real project directory is read-only context; do not write code changes directly there. "
        "Your writable code workspace is the private checkout at the current working directory. "
        "Submit code changes with `python -m multi_agent_tcp.workspace_api submit` after editing the private checkout.\n\n"
        f"{workspace_api_doc()}"
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
            protected_readonly_roots=[project_context],
        )
        adapter_options.setdefault("codex_home", str(codex_home))
        adapter_options.setdefault("skip_git_repo_check", True)

    existing = adapter_options.get("prompt_preamble")
    if isinstance(existing, str) and existing.strip():
        adapter_options["prompt_preamble"] = f"{existing.strip()}\n\n{preamble}"
    else:
        adapter_options["prompt_preamble"] = preamble

    execution_context = dict(adapter_options.get("execution_context", {}))
    execution_context["workspace_api"] = {
        "command": "python -m multi_agent_tcp.workspace_api",
        "context_env": WORKSPACE_API_CONTEXT_ENV,
        "areas": ["artifacts", "reports"],
        "transport": "rpc",
        "rpc_url": rpc_server.url,
    }
    execution_context["code_workspace"] = {
        "mode": "vcs_checkout",
        "project_context": str(project_context),
        "integration_dir": str(run.integration_dir),
        "checkout_path": str(checkout.checkout_dir),
        "checkout_id": checkout.checkout_id,
        "base_ref": checkout.base_ref,
        "write_scope": list(checkout.write_scope),
        "submit_command": "python -m multi_agent_tcp.workspace_api submit",
    }
    execution_context["private_context"] = {
        "private_dir": str(private_dir),
        "codex_home": str(codex_home),
        "agents_md": str(checkout.checkout_dir / "AGENTS.md"),
        "skill_catalog": skill_catalog,
        "rule_catalog": rule_catalog,
    }
    execution_context["workspace_scopes"] = ["run"]
    adapter_options["execution_context"] = execution_context
    data["adapter_options"] = adapter_options

    extra_env = {str(k): str(v) for k, v in dict(data.get("extra_env", {})).items()}
    extra_env[WORKSPACE_API_CONTEXT_ENV] = str(api_context_path)
    package_parent = str(Path(__file__).resolve().parent.parent)
    existing_pythonpath = extra_env.get("PYTHONPATH") or os.environ.get("PYTHONPATH")
    extra_env["PYTHONPATH"] = (
        f"{package_parent}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else package_parent
    )
    data["extra_env"] = extra_env
    return AgentNode.from_dict(data)
