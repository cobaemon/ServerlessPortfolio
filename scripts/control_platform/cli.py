"""Command-line interface for Control Platform v2."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.control_platform import engine
else:
    from . import engine


def main(argv: list[str] | None = None) -> int:
    """Run v2 validation, policy evaluation, self-test, or GitHook checks."""

    parser = argparse.ArgumentParser(description="Control Platform v2 CLI")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--classify-prompt")
    parser.add_argument("--eval-command")
    parser.add_argument("--eval-report")
    parser.add_argument("--contract-prompt", default="")
    parser.add_argument("--actor", default=None)
    parser.add_argument("--validate-policy", action="store_true")
    parser.add_argument("--validate-hooks", action="store_true")
    parser.add_argument("--validate-githooks", action="store_true")
    parser.add_argument("--validate-rag-sources", action="store_true")
    parser.add_argument("--validate-skills", action="store_true")
    parser.add_argument("--validate-stg-procedure", action="store_true")
    parser.add_argument("--git-hook", choices=["pre-commit", "commit-msg", "pre-push"])
    parser.add_argument("git_hook_args", nargs="*")
    parser.add_argument("--case", help="Compatibility named case evaluator.")
    args = parser.parse_args(argv)

    actor = engine.normalize_actor(args.actor) if args.actor else "codex"
    git_actor = engine.normalize_actor(args.actor) if args.actor else engine.actor_from_environment()
    contract = engine.classify_prompt(args.contract_prompt) if args.contract_prompt else None

    if args.self_test:
        result = engine.run_self_test()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    if args.classify_prompt is not None:
        _print(engine.classify_prompt(args.classify_prompt).to_json_dict())
        return 0
    if args.eval_command is not None:
        _print(engine.evaluate_command(args.eval_command, contract, actor).to_json_dict())
        return 0
    if args.eval_report is not None:
        _print(engine.evaluate_report(args.eval_report, contract, actor).to_json_dict())
        return 0
    if args.validate_policy:
        return _print_decision(engine.validate_policy())
    if args.validate_hooks:
        return _print_decision(engine.validate_hooks())
    if args.validate_githooks:
        return _print_decision(engine.validate_githooks())
    if args.validate_rag_sources:
        return _print_decision(engine.validate_rag_sources())
    if args.validate_skills:
        return _print_decision(engine.validate_skills_index())
    if args.validate_stg_procedure:
        return _print_decision(engine.validate_stg_procedure())
    if args.git_hook:
        msg_path = Path(args.git_hook_args[0]) if args.git_hook == "commit-msg" and args.git_hook_args else None
        decision = engine.evaluate_git_hook(args.git_hook, actor=git_actor, commit_msg_path=msg_path)
        _print(decision.to_json_dict())
        return 0 if decision.outcome in {"ALLOW", "WARN"} else 1
    if args.case:
        decision = _evaluate_compat_case(args.case, actor)
        _print(decision.to_json_dict())
        return 0 if decision.outcome in {"ALLOW", "WARN", "DENY", "NEEDS_EVIDENCE", "DENY_STOP_CONTINUE_PROCEDURE"} else 1

    parser.print_help()
    return 2


def _evaluate_compat_case(value: str, actor: str) -> engine.Decision:
    """Evaluate legacy --case inputs without keeping the old v1 engine."""

    deploy_contract = engine.Contract("DEPLOY_ALLOWED", ["FIXED_PROCEDURE_BOUND"], "compat", fixed_procedure=True)
    perf_contract = engine.Contract("PERFORMANCE_EXPERIMENT", ["PERFORMANCE_EXPERIMENT"], "compat", performance_experiment=True)
    lowered = value.lower()
    if "report" in lowered or "報告" in value or "verified" in lowered:
        return engine.evaluate_report(value, perf_contract if "performance" in lowered else None, actor)
    if "stg deploy" in lowered or "fixed procedure" in lowered:
        return engine.evaluate_report(value, deploy_contract, actor)
    return engine.evaluate_command(value, engine.Contract("IMPLEMENTATION_ALLOWED", turn_hash="compat"), actor)


def _print_decision(decision: engine.Decision) -> int:
    """Print a decision and return shell status for validation commands."""

    _print(decision.to_json_dict())
    return 0 if decision.outcome in {"ALLOW", "WARN"} else 1


def _print(data: dict[str, object]) -> None:
    """Print stable JSON for callers and tests."""

    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
