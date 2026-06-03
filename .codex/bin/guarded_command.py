"""PATH wrapper entrypoint that checks commands before execing the real binary."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.control import policy_engine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Validate argv with policy_engine and exec the real binary on ALLOW/WARN."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("guarded_command requires the target command name", file=sys.stderr)
        return 127
    command_name = args[0]
    command_args = args[1:]
    command_text = " ".join([command_name, *command_args])
    actor = policy_engine._actor(os.environ.get("GUARD_ACTOR", "unknown"))
    deploy_allowed = os.environ.get("GUARD_DEPLOY_ALLOWED") == "1"
    contract = policy_engine.default_contract(actor, deploy_allowed=deploy_allowed)
    decision = policy_engine.evaluate_deploy(contract, command_text, os.environ)
    if decision.outcome == "DENY":
        print(json.dumps(decision.to_json_dict(), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 126
    real_binary = _find_real_binary(command_name)
    if not real_binary:
        print(f"real binary not found for guarded command: {command_name}", file=sys.stderr)
        return 127
    os.execv(real_binary, [real_binary, *command_args])
    return 127


def _find_real_binary(command_name: str) -> str:
    """Find the target binary while excluding .codex/bin from PATH lookup."""
    if command_name == "python" and os.environ.get("GUARD_REAL_PYTHON"):
        return str(Path(os.environ["GUARD_REAL_PYTHON"]))
    wrapper_dir = str((REPO_ROOT / ".codex" / "bin").resolve())
    path_parts = [
        part
        for part in os.environ.get("PATH", "").split(os.pathsep)
        if part and str(Path(part).resolve()) != wrapper_dir
    ]
    return shutil.which(command_name, path=os.pathsep.join(path_parts)) or ""


if __name__ == "__main__":
    raise SystemExit(main())
