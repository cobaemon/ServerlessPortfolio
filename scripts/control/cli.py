"""Command-line adapter for policy validation, hooks, wrappers, and self-test."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.control import git_policy, policy_engine, self_test
from scripts.control.principles import (
    REPO_ROOT,
    iter_test_case_files,
    load_assets,
    load_control_file,
    load_invariants,
    load_principles,
    load_procedures,
)


REQUIRED_HOOK_EVENTS = {
    "SessionStart",
    "SubagentStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SubagentStop",
    "Stop",
}


def main(argv: list[str] | None = None) -> int:
    """Run the control CLI."""
    parser = argparse.ArgumentParser(description="ServerlessPortfolio comprehensive control gate")
    parser.add_argument("--validate-policy", action="store_true")
    parser.add_argument("--validate-hooks", action="store_true")
    parser.add_argument("--validate-githooks", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--case", default="")
    parser.add_argument("--pre-commit-test", action="store_true")
    parser.add_argument("--commit-msg-test", action="store_true")
    parser.add_argument("--pre-push-test", action="store_true")
    parser.add_argument("--git-hook", choices=["pre-commit", "commit-msg", "pre-push"])
    parser.add_argument("hook_args", nargs="*")
    args = parser.parse_args(argv)
    try:
        if args.validate_policy:
            return _print_result(_validate_policy())
        if args.validate_hooks:
            return _print_result(_validate_hooks())
        if args.validate_githooks:
            return _print_result(_validate_githooks())
        if args.self_test:
            report = self_test.run_self_test()
            print(json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            return 1 if report.failed else 0
        if args.case:
            return _evaluate_case(args.case)
        if args.pre_commit_test:
            return _print_decision(policy_engine._decision_from_mapping(git_policy.evaluate_git_change(hook_type="pre-commit", actor="codex", staged_diff="diff --git a/x b/x\n+safe line\n")))
        if args.commit_msg_test:
            return _print_decision(policy_engine._decision_from_mapping(git_policy.evaluate_git_change(hook_type="commit-msg", actor="codex", commit_message="制御を更新\n\n要件: AC\n検証: self-test\n")))
        if args.pre_push_test:
            return _print_decision(policy_engine._decision_from_mapping(git_policy.evaluate_git_change(hook_type="pre-push", actor="codex", push_refs="refs/heads/codex/control refs/heads/codex/control\n")))
        if args.git_hook:
            return _run_git_hook(args.git_hook, args.hook_args)
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed for AI/CI actors.
        print(json.dumps({"outcome": "ERROR", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    parser.print_help()
    return 2


def _validate_policy() -> dict[str, object]:
    """Validate control documents and required policy registry facts."""
    principles = load_principles()
    invariants = load_invariants()
    assets = load_assets()
    procedures = load_procedures()
    for filename in ("principles.yml", "invariants.yml", "assets.yml", "procedures.yml", "report_schema.yml"):
        load_control_file(filename)
    principle_ids = [item["id"] for item in principles["principles"]]
    if principle_ids != ["P1", "P2", "P3", "P4"]:
        raise ValueError(f"invalid principle order: {principle_ids}")
    priorities = [item["priority"] for item in principles["principles"]]
    if priorities != [1, 2, 3, 4]:
        raise ValueError(f"invalid priority order: {priorities}")
    invariant_ids = {item["id"] for item in invariants["invariants"]}
    required_invariants = {"INV-P1-001", "INV-P1-003", "INV-P2-002", "INV-P3-001", "INV-P3-002", "INV-P4-001"}
    missing = required_invariants.difference(invariant_ids)
    if missing:
        raise ValueError("missing invariants: " + ", ".join(sorted(missing)))
    if not assets["prohibited_assets"] or not assets["allowed_assets"]:
        raise ValueError("assets policy must contain allowed and prohibited assets")
    if not procedures["fixed_procedures"]:
        raise ValueError("procedures must contain fixed procedures")
    _validate_wrapper_files()
    _validate_ci_gate_files()
    test_files = [path.name for path in iter_test_case_files()]
    return {"outcome": "ALLOW", "reason": "policy registry is valid", "test_case_files": test_files}


def _validate_hooks() -> dict[str, object]:
    """Validate Codex hook JSON and adapter connection."""
    path = REPO_ROOT / ".codex" / "hooks.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    hooks = data.get("hooks", {})
    missing_events = REQUIRED_HOOK_EVENTS.difference(hooks)
    if missing_events:
        raise ValueError("missing hook events: " + ", ".join(sorted(missing_events)))
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            raise ValueError(f"hook event must be a list: {event}")
        for entry in entries:
            for hook in entry.get("hooks", []):
                command = str(hook.get("command", ""))
                timeout = int(hook.get("timeout", 0))
                if ".codex/hooks/codex_hook_adapter.py" not in command.replace("\\", "/"):
                    raise ValueError(f"hook does not use common adapter: {event}")
                if timeout <= 0 or timeout > 10:
                    raise ValueError(f"hook timeout must be 1..10 seconds: {event}")
    return {"outcome": "ALLOW", "reason": "hooks JSON is valid", "events": sorted(hooks)}


def _validate_githooks() -> dict[str, object]:
    """Validate local GitHook files use the shared policy CLI."""
    required = ["pre-commit", "commit-msg", "pre-push"]
    for name in required:
        path = REPO_ROOT / ".githooks" / name
        text = path.read_text(encoding="utf-8")
        if "scripts.control.cli" not in text:
            raise ValueError(f"GitHook does not call policy CLI: {name}")
        if "--no-verify" in text:
            raise ValueError(f"GitHook contains bypass wording: {name}")
    return {"outcome": "ALLOW", "reason": "GitHook files are valid", "hooks": required}


def _validate_wrapper_files() -> None:
    """Validate PATH wrapper files use the shared guarded command adapter."""
    required = ["git", "aws", "sam", "npm", "pnpm", "yarn", "pip", "python", "rg", "grep", "find", "powershell", "pwsh"]
    guarded = REPO_ROOT / ".codex" / "bin" / "guarded_command.py"
    if "policy_engine" not in guarded.read_text(encoding="utf-8"):
        raise ValueError("guarded_command.py does not call policy_engine")
    for name in required:
        text = (REPO_ROOT / ".codex" / "bin" / name).read_text(encoding="utf-8")
        if "guarded_command.py" not in text:
            raise ValueError(f"wrapper does not call guarded_command.py: {name}")


def _validate_ci_gate_files() -> None:
    """Validate CI buildspec files call the shared policy CLI before installs."""
    required_commands = [
        "python -B -m scripts.control.cli --validate-policy",
        "python -B -m scripts.control.cli --validate-hooks",
        "python -B -m scripts.control.cli --validate-githooks",
        "python -B -m scripts.control.cli --self-test",
    ]
    for name in ("buildspec.yml", "buildspec-deps.yml"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        missing = [command for command in required_commands if command not in text]
        if missing:
            raise ValueError(f"{name} lacks CI control commands: {', '.join(missing)}")


def _evaluate_case(command: str) -> int:
    """Evaluate a single representative shell case and print the decision."""
    contract = policy_engine.default_contract("codex")
    decision = policy_engine.evaluate_deploy(contract, command, os.environ)
    print(json.dumps(decision.to_json_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_git_hook(hook_type: str, hook_args: list[str]) -> int:
    """Run a local GitHook and return a hook-compatible exit code."""
    actor = policy_engine._actor(os.environ.get("GUARD_ACTOR", "unknown"))
    if hook_type == "pre-commit":
        staged_diff = _git_text(["diff", "--cached"])
        result = git_policy.evaluate_git_change(hook_type=hook_type, actor=actor, staged_diff=staged_diff)
    elif hook_type == "commit-msg":
        if not hook_args:
            raise ValueError("commit-msg hook requires the commit message path")
        message = Path(hook_args[0]).read_text(encoding="utf-8")
        result = git_policy.evaluate_git_change(hook_type=hook_type, actor=actor, commit_message=message)
    else:
        push_refs = sys.stdin.read()
        result = git_policy.evaluate_git_change(hook_type=hook_type, actor=actor, push_refs=push_refs)
    decision = policy_engine._decision_from_mapping(result)
    return _print_decision(decision, hook_mode=True)


def _git_text(args: list[str]) -> str:
    """Return git command output for local hook inspection."""
    completed = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def _print_result(data: dict[str, object]) -> int:
    """Print a validation result."""
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _print_decision(decision: policy_engine.Decision, *, hook_mode: bool = False) -> int:
    """Print a decision and optionally enforce hook exit semantics."""
    print(json.dumps(decision.to_json_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if hook_mode and decision.outcome == "DENY":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
