from __future__ import annotations

import importlib.metadata as importlib_metadata
import sys
from pathlib import Path
from typing import Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parent
_VENDOR_RYVEN = _REPO_ROOT / "vendor" / "ryven"
_VENDOR_RYVENCORE_QT = _REPO_ROOT / "vendor" / "ryvencore_qt"
_BLUEPRINT_NODES_PACKAGE = _REPO_ROOT / "ryven_blueprint_nodes"


def _ensure_vendor_paths() -> None:
    for path in (_VENDOR_RYVENCORE_QT, _VENDOR_RYVEN):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    for path in (_REPO_ROOT.parent, _REPO_ROOT):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.append(path_str)


def _patch_ryven_version_lookup() -> None:
    real_version = importlib_metadata.version

    def patched_version(name: str) -> str:
        if name == "ryven":
            return "0.0.0"
        return real_version(name)

    importlib_metadata.version = patched_version



def run(argv: Optional[Sequence[str]] = None) -> None:
    _ensure_vendor_paths()
    _patch_ryven_version_lookup()

    import ryven

    args = list(argv) if argv is not None else sys.argv[1:]
    if "-q" not in args and "--qt-api" not in args:
        args = [*args, "-q", "pyside6"]
    if str(_BLUEPRINT_NODES_PACKAGE) not in args:
        args = [*args, "-n", str(_BLUEPRINT_NODES_PACKAGE)]

    sys.argv = ["ryven", *args]
    ryven.run_ryven()


if __name__ == "__main__":
    run()
