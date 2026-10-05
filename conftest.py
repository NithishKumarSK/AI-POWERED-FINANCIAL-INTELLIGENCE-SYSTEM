"""Repo-wide pytest bootstrap. Loaded automatically before test collection,
so every test file's existing bare imports (from the legacy pipeline, the
core/ utilities, etc.) resolve correctly after the repo reorganization --
without needing to touch the hundreds of individual import sites across
tests/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bootstrap_paths  # noqa: E402

bootstrap_paths.add_module_paths()
