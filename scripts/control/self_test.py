"""Self-test runner for invariant categories and representative cases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from scripts.control import incident_policy, policy_engine
from scripts.control.principles import iter_test_case_files, load_test_case_file


REGRESSION_CATEGORIES = [
    "prompt_contract",
    "explicit_permission",
    "ambiguity_gate",
    "asset_reachability",
    "hidden_ignored_enumeration",
    "pathless_recursive_listing",
    "shell_expansion",
    "external_path",
    "secret_protection",
    "git_branch",
    "git_push",
    "deploy",
    "aws_profile_region",
    "external_tool_license",
    "report_claim",
    "incident_lifecycle",
    "stop_loop",
    "human_not_blocked",
    "principle_priority",
    "fallback_forbidden",
    "unused_control",
]


@dataclass
class TestReport:
    """Self-test result summary."""

    passed: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    regression_categories: list[str] = field(default_factory=lambda: list(REGRESSION_CATEGORIES))

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable result."""
        return {
            "passed": self.passed,
            "failed": self.failed,
            "failures": self.failures,
            "categories": sorted(set(self.categories)),
            "regression_categories": self.regression_categories,
        }


def run_self_test() -> TestReport:
    """Run all case files without network, AWS, deploy, or build execution."""
    report = TestReport()
    for path in iter_test_case_files():
        document = load_test_case_file(path)
        category = str(document.get("category", path.stem))
        report.categories.append(category)
        cases = document.get("cases", [])
        if not isinstance(cases, list):
            _fail(report, f"{path.name}: cases must be a list")
            continue
        for case in cases:
            _run_case(report, category, case)
    _check_required_categories(report)
    return report


def main() -> int:
    """CLI entrypoint for self-test execution."""
    report = run_self_test()
    print(json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report.failed else 0


def _run_case(report: TestReport, category: str, case: Any) -> None:
    """Run one test case and compare its expected decision."""
    if not isinstance(case, dict):
        _fail(report, f"{category}: case must be an object")
        return
    kind = str(case.get("kind", "command"))
    actor = str(case.get("actor", "codex"))
    deploy_allowed = bool(case.get("deploy_allowed", False))
    contract = policy_engine.default_contract(policy_engine._actor(actor), deploy_allowed=deploy_allowed)
    text = str(case.get("input", ""))
    expected = case.get("expected")
    if kind == "prompt":
        classified = policy_engine.classify_prompt(text, policy_engine.RuntimeContext(actor=policy_engine._actor(actor)))
        _assert_prompt_case(report, case, classified)
        return
    if kind in {"command", "deploy_command"}:
        decision = policy_engine.evaluate_deploy(contract, text, case.get("env", {}))
    elif kind == "report":
        decision = policy_engine.evaluate_report(contract, text)
    elif kind == "stop":
        decision = policy_engine.evaluate_report(contract, text, stop_event=True)
    elif kind == "incident":
        decision = policy_engine._decision_from_mapping(incident_policy.evaluate_incident_record_text(text))
    else:
        _fail(report, f"{case.get('id', '<unknown>')}: unknown case kind {kind}")
        return
    if expected and decision.outcome != expected:
        _fail(report, f"{case.get('id', '<unknown>')}: expected {expected}, got {decision.outcome}: {decision.reason}")
    else:
        report.passed += 1


def _assert_prompt_case(report: TestReport, case: dict[str, object], contract: policy_engine.Contract) -> None:
    """Assert prompt contract work-type expectations."""
    expected_present = case.get("assert_work_type")
    expected_absent = case.get("assert_work_type_absent")
    if expected_present and str(expected_present) not in contract.work_type:
        _fail(report, f"{case.get('id', '<unknown>')}: missing work type {expected_present}")
        return
    if expected_absent and str(expected_absent) in contract.work_type:
        _fail(report, f"{case.get('id', '<unknown>')}: unexpected work type {expected_absent}")
        return
    report.passed += 1


def _check_required_categories(report: TestReport) -> None:
    """Ensure negative, positive, stop-loop, and human categories are present."""
    required_files = {
        "prompt_contract",
        "asset_reachability",
        "command",
        "git",
        "deploy",
        "report",
        "incident",
        "stop_loop",
        "human_not_blocked",
    }
    missing = required_files.difference(set(report.categories))
    if missing:
        _fail(report, "missing self-test categories: " + ", ".join(sorted(missing)))


def _fail(report: TestReport, message: str) -> None:
    """Record a self-test failure."""
    report.failed += 1
    report.failures.append(message)


if __name__ == "__main__":
    raise SystemExit(main())
