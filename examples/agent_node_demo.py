"""Minimal AgentNode runtime demo.

Run from the repository parent:

    python -m multi_agent_tcp.examples.agent_node_demo

This demo intentionally uses an in-process fake cluster. It exercises the
AgentNode and GraphRuntime contracts without starting CodeMaker/Codex.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from multi_agent_tcp import (
    AgentNode,
    GraphRuntime,
    SuperAgentProfile,
    WorkerConfig,
    WorkspaceManifest,
)
from multi_agent_tcp.skill_space import SkillSpace


class DemoCluster:
    """Small stand-in for CLIWorkerBackend used by GraphRuntime."""

    def __init__(self) -> None:
        self.started_workers: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []

    async def ensure_worker(self, worker: WorkerConfig) -> None:
        self.started_workers.append(
            {
                "agent_id": worker.agent_id,
                "cli_kind": worker.cli_kind,
                "model": worker.model,
                "cwd": str(worker.cwd),
                "adapter_options_keys": sorted(worker.adapter_options),
            }
        )

    async def run_single(
        self,
        worker_id: str,
        body: Any,
        *,
        timeout_sec: float = 600.0,
        _skip_skill_inject: bool = False,
    ) -> dict[str, Any]:
        self.messages.append(
            {
                "worker_id": worker_id,
                "body": body,
                "timeout_sec": timeout_sec,
            }
        )
        return {
            "type": "message",
            "from": worker_id,
            "body": {
                "ok": True,
                "echo_prompt": body.get("prompt") if isinstance(body, dict) else body,
                "message_index": len(self.messages),
            },
        }


def make_skill(root: Path, name: str, description: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n",
        encoding="utf-8",
    )
    return skill_dir


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agent-node-demo-") as tmp:
        root = Path(tmp)

        # Framework-owned skill space: users choose by mode, runtime resolves
        # to hashes and materializes only authorized skills for this agent.
        source_skills = root / "source-skills"
        skill_space = SkillSpace.open_or_init(root / "skill-space")
        pytest_skill = skill_space.add_skill_copy(
            make_skill(source_skills, "pytest-debug", "Debug pytest failures")
        )
        docs_skill = skill_space.add_skill_copy(
            make_skill(source_skills, "docs-summarize", "Summarize local docs")
        )

        blocking_node = AgentNode.from_dict(
            {
                # node_id intentionally omitted: framework allocates it.
                "agent_id": "agent-codex-demo",
                "cli_kind": "codex",
                "model": "gpt-5.4",
                "cwd": str(root / "project"),
                "timeout_sec": 30,
                "skill_selection": {
                    "mode": "selected",
                    "skill_hashes": [pytest_skill.skill_hash],
                },
            }
        )
        selected_hashes = blocking_node.resolve_skill_hashes(skill_space)
        skill_view = skill_space.materialize_for_agent(
            agent_id=blocking_node.runtime_agent_id,
            agent_root=root / "run" / "agents" / blocking_node.runtime_agent_id,
            skill_hashes=selected_hashes,
        )
        blocking_node.adapter_options.update(skill_view.codex_adapter_options())

        super_agent = SuperAgentProfile(
            agent_id="supervisor",
            assignable_skill_hashes=[docs_skill.skill_hash],
        )
        nonblocking_node = AgentNode.from_dict(
            {
                "agent_id": "agent-background-demo",
                "execution_mode": "nonblocking",
                "cli_kind": "codemaker",
                "cwd": str(root / "project"),
                "workspace_id": "demo-workspace",
                "workspace_root": str(root / "workspace"),
                "write_scope": ["outputs"],
                "skill_selection": {"mode": "upstream", "assigned_by": "supervisor"},
            }
        )
        upstream_hashes = nonblocking_node.resolve_skill_hashes(
            skill_space,
            upstream_super_agent=super_agent,
            upstream_skill_hashes=[docs_skill.skill_hash],
        )

        cluster = DemoCluster()
        workspace = WorkspaceManifest("demo-workspace", root / "workspace")
        async with GraphRuntime(cluster, workspace=workspace) as runtime:
            first_reply = await runtime.send_agent_message(
                blocking_node,
                {"prompt": "Use the authorized pytest skill."},
            )
            second_reply = await runtime.send_agent_message(
                blocking_node,
                {"prompt": "Reuse the same AgentNode binding."},
            )
            job = await runtime.submit_agent_job(
                nonblocking_node,
                {"prompt": "Run this as a background node job."},
                job_id="job-demo",
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)

            output = {
                "blocking_node": {
                    "node_id": blocking_node.node_id,
                    "runtime_agent_id": blocking_node.runtime_agent_id,
                    "skill_selection": blocking_node.skill_selection.to_dict(),
                    "resolved_skill_hashes": selected_hashes,
                    "materialized_skill_names": [
                        row["name"] for row in skill_view.catalog
                    ],
                    "worker_config": blocking_node.to_worker_config().to_agent_json(
                        "127.0.0.1",
                        9140,
                    ),
                    "replies": [first_reply, second_reply],
                },
                "nonblocking_node": {
                    "node_id": nonblocking_node.node_id,
                    "runtime_agent_id": nonblocking_node.runtime_agent_id,
                    "skill_selection": nonblocking_node.skill_selection.to_dict(),
                    "upstream_assigned_hashes": upstream_hashes,
                    "job": {
                        "job_id": job.job_id,
                        "status": job.status,
                    },
                },
                "runtime": {
                    "started_workers": cluster.started_workers,
                    "messages_sent": cluster.messages,
                    "events": [event.to_dict() for event in runtime.events],
                    "workspace_manifest": workspace.to_dict(),
                    "bound_instances": {
                        node_id: {
                            "agent_id": inst.agent_id,
                            "messages_sent": inst.messages_sent,
                        }
                        for node_id, inst in runtime.instances.items()
                    },
                },
            }

        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
