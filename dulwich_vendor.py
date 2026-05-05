"""Import helper for the vendored Dulwich checkout."""

from __future__ import annotations

import sys
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent
_VENDOR_DULWICH = _MODULE_DIR / "vendor" / "dulwich"


def ensure_dulwich_path() -> None:
    """Put the vendored Dulwich checkout on sys.path if needed."""
    path = _VENDOR_DULWICH
    if not path.is_dir():
        raise ImportError(f"vendored Dulwich checkout not found: {path}")
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
