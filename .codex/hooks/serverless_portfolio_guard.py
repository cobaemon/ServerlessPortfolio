#!/usr/bin/env python3
"""CodexHook wrapper for the shared project control guard."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    """Run the shared guard from the repository root."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "project_control_guard.py"
    sys.argv = [str(script), *sys.argv[1:]]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
