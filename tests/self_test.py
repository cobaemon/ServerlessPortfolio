#!/usr/bin/env python3
"""Run Control Platform v2 self-tests from the repository test entrypoint."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.control_platform.engine import run_self_test  # noqa: E402


def main() -> int:
    """Print one line per invariant self-test and return failing status."""

    report = run_self_test()
    for item in report["tests"]:
        status = "PASS" if item["ok"] else "FAIL"
        print(f"{status}: {item['name']} -> {item['actual']} ({item['reason']})")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
