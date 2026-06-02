"""Test: launch one Codex CLI agent with skill catalog, verify on-demand read.

Usage:
    python -m multi_agent_tcp.test_skill_injection [--agent-id agent-1] [--skill excel-export-flow]
    python -m multi_agent_tcp.test_skill_injection --mode full   # legacy full-inject mode

This script:
1. Loads the agents registry
2. Builds a lightweight skill catalog (or full preamble in --mode full)
3. Launches a single CLI-backed worker via CLIWorkerBackend
4. Sends a prompt that asks the agent to read the skill file and summarize it
5. Prints whether the agent successfully loaded the skill on-demand
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .registry import AgentsRegistry
from .cli_worker_backend import CLIWorkerBackend, WorkerConfig
from .log_setup import setup_logging

log = logging.getLogger(__name__)


async def run_test(
    agent_id: str,
    skill_name: str,
    mode: str,
    verbose: bool,
) -> None:
    setup_logging(verbose, "test_skill_injection")
    reg = AgentsRegistry.load()

    available_skills = reg.list_available_skills()
    if skill_name not in available_skills:
        print(f"ERROR: skill {skill_name!r} not in skill_list/. "
              f"Available: {available_skills[:10]}...")
        sys.exit(1)

    agent = reg.get_agent(agent_id)
    skill_info = reg.get_skill_info(skill_name)
    print(f"Agent:  {agent.agent_id} ({agent.display_name})")
    print(f"Model:  {agent.model}")
    print(f"CWD:    {agent.cwd}")
    print(f"Skills: {agent.skills}")
    print(f"Mode:   {mode}")
    print(f"Test skill: {skill_name}")
    print(f"  path: {skill_info.skill_md_path}")
    print(f"  desc: {skill_info.description}")
    print()

    if mode == "catalog":
        catalog = reg.build_skill_catalog(agent_id)
        print(f"Catalog size: {len(catalog)} chars")
        print("--- catalog preview ---")
        print(catalog[:600])
        print("--- end preview ---\n")

        task_text = (
            f"I need you to verify you can use the skill catalog.\n\n"
            f"1. Look at the skill catalog above.\n"
            f"2. Find the skill named '{skill_name}' in the table.\n"
            f"3. Read the SKILL.md file at the path shown in the table.\n"
            f"4. After reading, answer:\n"
            f"   a) What is the skill name?\n"
            f"   b) Summarize what the skill does (1-2 sentences).\n"
            f"   c) List the first 3 section headings.\n"
            f"   d) Confirm: did you successfully read the file? (yes/no)\n\n"
            f"You MUST use the read tool to load the SKILL.md file. "
            f"Do NOT guess — actually read it."
        )
        prompt = reg.inject_skills_into_prompt(agent_id, task_text, mode="catalog")
    else:
        task_text = (
            f"Verify you received the skill '{skill_name}':\n"
            f"1. What is the skill name?\n"
            f"2. Summarize in 1-2 sentences.\n"
            f"3. First 3 section headings.\n"
            f"4. Can you use it? (yes/no)"
        )
        prompt = reg.inject_skills_into_prompt(agent_id, task_text, mode="full")

    print(f"Total prompt size: {len(prompt)} chars\n")

    wc = WorkerConfig(
        agent_id=agent.agent_id,
        cwd=Path(agent.cwd),
        model=agent.model,
        timeout_sec=agent.timeout_sec,
    )

    print("Launching cluster with 1 worker...")
    async with await CLIWorkerBackend.create(workers=[wc], port=9150) as cluster:
        print(f"Cluster up. Sending prompt...\n")

        result = await cluster.run_single(
            agent.agent_id,
            {"prompt": prompt},
        )

        body = result.get("body", {})
        codex = body.get("codex", {}) if isinstance(body, dict) else {}
        stderr_raw = codex.get("stderr", "") if isinstance(codex, dict) else ""
        rc = codex.get("returncode", -1) if isinstance(codex, dict) else -1
        answer = (
            str(codex.get("final_text") or codex.get("last_message") or "")
            if isinstance(codex, dict)
            else ""
        )

        print("=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Return code: {rc}")
        if stderr_raw.strip():
            stderr_preview = stderr_raw[:500]
            print(f"Stderr (first 500): {stderr_preview}")
        print()
        print("Agent answer:")
        print("-" * 60)
        print(answer if answer else "(no answer extracted)")
        print("-" * 60)

        out_path = Path(__file__).resolve().parent / "logs" / "test_skill_injection_result.json"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(
            json.dumps({
                "agent_id": agent.agent_id,
                "skill_tested": skill_name,
                "model": agent.model,
                "mode": mode,
                "prompt_chars": len(prompt),
                "returncode": rc,
                "answer": answer,
                "answer_length": len(answer) if answer else 0,
                "stderr_head": stderr_raw[:300],
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nResult saved to {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Test skill injection into Codex CLI agent")
    ap.add_argument("--agent-id", default="agent-1",
                    help="Agent ID from registry")
    ap.add_argument("--skill", default="excel-export-flow",
                    help="Skill name to test")
    ap.add_argument("--mode", choices=["catalog", "full"], default="catalog",
                    help="catalog = lightweight table + on-demand read; "
                         "full = embed full SKILL.md (legacy)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    asyncio.run(run_test(args.agent_id, args.skill, args.mode, args.verbose))


if __name__ == "__main__":
    main()
