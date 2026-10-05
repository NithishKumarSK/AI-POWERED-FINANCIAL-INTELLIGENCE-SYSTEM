"""Single source of truth for making every subfolder's modules importable by
bare name (e.g. `from record_dedup import dedup_records`), regardless of
which subfolder the importing code or the imported module lives in.

The codebase has always relied on sys.path manipulation for this (every
entry point already does `sys.path.insert(0, ROOT)` / `sys.path.insert(1,
ROOT/"tools")`) -- this just centralizes that pattern instead of repeating
the subfolder list at every entry point, so adding a new organized
subfolder later means updating one file, not every launcher.

Call `add_module_paths()` once, as early as possible, from any entry point
(a script run directly, `backend/main.py`, a pytest `conftest.py`, etc.)
before importing anything that lives in one of these subfolders.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

_MODULE_SUBFOLDERS = ("core", "legacy", "agents", "tools", "src", "db")


def add_module_paths() -> None:
    root_s = str(ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    for sub in _MODULE_SUBFOLDERS:
        p = str(ROOT / sub)
        if p not in sys.path:
            sys.path.insert(0, p)
