"""Merge skills from .cursor/skills into skill_list/.

Usage:
    python -m multi_agent_tcp.init_skill_list [--force]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List

_WORKSPACE = Path(__file__).resolve().parent.parent  # Package/Script/Python
_CURSOR_SKILLS = _WORKSPACE / ".cursor" / "skills"
_SKILL_LIST_DIR = Path(__file__).resolve().parent / "skill_list"

_IGNORE_PATTERNS = {"__pycache__", ".git", "node_modules"}


def _discover_skills(root: Path) -> Dict[str, Path]:
    """Return {skill_name: skill_dir} for dirs that contain SKILL.md."""
    if not root.is_dir():
        return {}
    result: Dict[str, Path] = {}
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            result[child.name] = child
    return result


def _copy_skill(src: Path, dst: Path) -> int:
    """Copy a skill directory tree, return file count."""
    if dst.exists():
        shutil.rmtree(dst)
    count = 0

    def _ignore(directory: str, contents: List[str]) -> List[str]:
        return [c for c in contents if c in _IGNORE_PATTERNS]

    shutil.copytree(str(src), str(dst), ignore=_ignore)
    for _ in dst.rglob("*"):
        count += 1
    return count


def merge_skills(*, force: bool = False) -> Dict[str, dict]:
    """Merge the configured skill source into skill_list/. Returns manifest dict."""
    if _SKILL_LIST_DIR.exists():
        if not force:
            print(f"skill_list/ already exists. Use --force to overwrite.", file=sys.stderr)
            sys.exit(1)
        shutil.rmtree(_SKILL_LIST_DIR)
    _SKILL_LIST_DIR.mkdir(parents=True)

    cursor_skills = _discover_skills(_CURSOR_SKILLS)

    all_names = sorted(cursor_skills)
    manifest: Dict[str, dict] = {}

    for name in all_names:
        src = cursor_skills[name]
        source = ".cursor/skills"
        override = False

        dst = _SKILL_LIST_DIR / name
        file_count = _copy_skill(src, dst)

        skill_md = dst / "SKILL.md"
        description = ""
        if skill_md.is_file():
            for line in skill_md.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    description = stripped.lstrip("# ").strip()
                    break

        manifest[name] = {
            "source": source,
            "override": override,
            "file_count": file_count,
            "description": description[:120],
        }
        tag = " (override .cursor)" if override else ""
        print(f"  [{source}]{tag} {name} ({file_count} files)")

    manifest_path = _SKILL_LIST_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nMerged {len(manifest)} skills → {_SKILL_LIST_DIR}")
    print(f"Manifest written to {manifest_path}")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge skills into skill_list/")
    ap.add_argument("--force", action="store_true", help="Overwrite existing skill_list/")
    args = ap.parse_args()
    merge_skills(force=args.force)


if __name__ == "__main__":
    main()
