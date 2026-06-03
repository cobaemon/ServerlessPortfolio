"""Load the project control policy documents from the controls directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PolicyLoadError(RuntimeError):
    """Raised when a control document cannot be loaded or validated."""


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_DIR = REPO_ROOT / "controls"
TEST_CASE_DIR = CONTROL_DIR / "test_cases"


def load_control_file(filename: str) -> dict[str, Any]:
    """Return one JSON-compatible YAML policy document by filename."""
    path = CONTROL_DIR / filename
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except FileNotFoundError as exc:
        raise PolicyLoadError(f"control file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyLoadError(f"control file is not JSON-compatible YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyLoadError(f"control file root must be an object: {path}")
    return data


def load_principles() -> dict[str, Any]:
    """Return the principle source of truth."""
    return load_control_file("principles.yml")


def load_invariants() -> dict[str, Any]:
    """Return machine-checkable invariants derived from the principles."""
    return load_control_file("invariants.yml")


def load_assets() -> dict[str, Any]:
    """Return allowed and prohibited asset classifications."""
    return load_control_file("assets.yml")


def load_report_schema() -> dict[str, Any]:
    """Return report and incident evidence requirements."""
    return load_control_file("report_schema.yml")


def load_procedures() -> dict[str, Any]:
    """Return fixed procedure definitions for connected gates."""
    return load_control_file("procedures.yml")


def iter_test_case_files() -> list[Path]:
    """Return all self-test case files in deterministic order."""
    if not TEST_CASE_DIR.exists():
        raise PolicyLoadError(f"test case directory is missing: {TEST_CASE_DIR}")
    return sorted(TEST_CASE_DIR.glob("*.yml"))


def load_test_case_file(path: Path) -> dict[str, Any]:
    """Return one self-test case document."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyLoadError(f"test case file is not JSON-compatible YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyLoadError(f"test case file root must be an object: {path}")
    return data
