"""Thin Codex hook adapter for Control Platform v2.

The adapter performs no deploy, AWS, build, package install, or network work.
It parses the hook payload, loads the current-turn contract, and delegates to
the shared policy engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.control_platform import engine
else:
    from . import engine

RUNTIME_DIR = engine.REPO_ROOT / ".codex" / "control_platform_runtime"
CONTRACT_FILE = RUNTIME_DIR / "current_contract.json"
STOP_FILE = RUNTIME_DIR / "stop_continuations.json"


def main() -> int:
    """Read hook JSON from stdin and emit Codex-compatible JSON."""

    payload = _read_payload()
    actor = engine.normalize_actor(os.environ.get("GUARD_ACTOR") or "codex")
    event = str(payload.get("hook_event_name") or payload.get("event") or "")

    if event == "UserPromptSubmit":
        prompt = _prompt_text(payload)
        contract = engine.classify_prompt(prompt)
        _write_contract(contract)
        _emit({"decision": "continue", "context": contract.to_json_dict()})
        return 0

    if event in {"SessionStart", "SubagentStart", "PreCompact", "PostCompact"}:
        decision = _startup_decision(actor)
        _emit({"decision": "continue" if decision.outcome in {"ALLOW", "WARN"} else "block", "policy": decision.to_json_dict()})
        return 0

    contract = _read_contract()
    if event == "PreToolUse":
        decision = engine.evaluate_tool_use(contract, str(payload.get("tool_name", "")), _dict(payload.get("tool_input")), actor)
        return _emit_permission_decision(decision)

    if event == "PermissionRequest":
        decision = engine.evaluate_permission_request(contract, payload, actor)
        return _emit_permission_decision(decision)

    if event == "PostToolUse":
        decision = engine.evaluate_tool_result(_dict(payload.get("tool_result") or payload), actor)
        if decision.outcome in {"DENY", "ERROR"}:
            _emit({"decision": "block", "reason": _safe_reason(decision), "policy": _minimal_decision(decision)})
        else:
            _emit({"decision": "continue", "policy": decision.to_json_dict()})
        return 0

    if event in {"Stop", "SubagentStop"}:
        decision = engine.evaluate_report(_report_text(payload), contract, actor)
        return _emit_stop_decision(contract, decision)

    decision = engine.Decision(
        "DENY" if actor != "human" else "WARN",
        ["INV-P1-PERMISSION"],
        f"Unknown hook event: {event or 'missing'}",
        ["Use a supported Control Platform v2 hook event."],
        ["hook_event_name"],
    )
    _emit({"decision": "block" if decision.outcome == "DENY" else "continue", "policy": decision.to_json_dict()})
    return 0


def _startup_decision(actor: str) -> engine.Decision:
    """Validate policy readability for lifecycle events."""

    policy_decision = engine.validate_policy()
    if policy_decision.outcome == "ALLOW":
        return policy_decision
    if actor == "human":
        return engine.Decision("WARN", policy_decision.invariant_ids, policy_decision.reason, policy_decision.allowed_next_actions, policy_decision.evidence_required)
    return policy_decision


def _read_payload() -> dict[str, Any]:
    """Parse hook input JSON safely."""

    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"hook_event_name": "Invalid", "raw_input_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]}
    return parsed if isinstance(parsed, dict) else {"hook_event_name": "Invalid"}


def _prompt_text(payload: dict[str, Any]) -> str:
    """Extract prompt text from known hook payload fields."""

    for key in ("prompt", "user_prompt", "message"):
        if payload.get(key):
            return str(payload[key])
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict) and tool_input.get("prompt"):
        return str(tool_input["prompt"])
    return ""


def _report_text(payload: dict[str, Any]) -> str:
    """Extract report text from known Stop/SubagentStop fields."""

    for key in ("response", "final_response", "message", "subagent_response"):
        if payload.get(key):
            return str(payload[key])
    return ""


def _dict(value: Any) -> dict[str, Any]:
    """Return a dictionary payload shape."""

    return value if isinstance(value, dict) else {}


def _write_contract(contract: engine.Contract) -> None:
    """Persist only hashed current-turn contract metadata for later hooks."""

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    CONTRACT_FILE.write_text(json.dumps(contract.to_json_dict(), ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _read_contract() -> engine.Contract:
    """Read the current-turn contract, failing to question-only if missing."""

    if not CONTRACT_FILE.exists():
        return engine.Contract("QUESTION_ONLY", turn_hash=engine.classify_prompt("").turn_hash)
    try:
        data = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return engine.Contract("QUESTION_ONLY", turn_hash=engine.classify_prompt("").turn_hash)
    return engine.Contract(
        work_type=str(data.get("work_type", "QUESTION_ONLY")),
        flags=list(data.get("flags", [])),
        turn_hash=str(data.get("turn_hash", "")),
        fixed_procedure=bool(data.get("fixed_procedure", False)),
        performance_experiment=bool(data.get("performance_experiment", False)),
        environment_mutation_allowed=bool(data.get("environment_mutation_allowed", False)),
        explicit_measurement_procedure=bool(data.get("explicit_measurement_procedure", False)),
        ambiguities=list(data.get("ambiguities", [])),
    )


def _emit_permission_decision(decision: engine.Decision) -> int:
    """Emit PreToolUse/PermissionRequest decision output."""

    if decision.outcome in {"DENY", "ERROR"}:
        _emit(
            {
                "permissionDecision": "deny",
                "permissionDecisionReason": _safe_reason(decision),
                "policy": _minimal_decision(decision),
            }
        )
        return 0
    _emit({"permissionDecision": "allow", "policy": decision.to_json_dict()})
    return 0


def _emit_stop_decision(contract: engine.Contract, decision: engine.Decision) -> int:
    """Emit Stop/SubagentStop output while limiting continuation loops."""

    if decision.outcome in {"NEEDS_EVIDENCE", "DENY_STOP_CONTINUE_PROCEDURE", "ERROR"}:
        if _consume_stop_continuation(contract, decision):
            _emit({"decision": "block", "reason": _safe_reason(decision), "policy": _minimal_decision(decision)})
        else:
            _emit(
                {
                    "decision": "continue",
                    "reason": "Continuation limit reached; allow failure report with unmet evidence explicitly stated.",
                    "policy": _minimal_decision(decision),
                }
            )
        return 0
    _emit({"decision": "continue", "policy": decision.to_json_dict()})
    return 0


def _consume_stop_continuation(contract: engine.Contract, decision: engine.Decision) -> bool:
    """Allow one continuation per same turn, invariant, and reason."""

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    key_text = f"{contract.turn_hash}|{','.join(decision.invariant_ids)}|{decision.reason}"
    key = hashlib.sha256(key_text.encode("utf-8")).hexdigest()
    state: dict[str, int] = {}
    if STOP_FILE.exists():
        try:
            state = json.loads(STOP_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    count = int(state.get(key, 0))
    if count >= 1:
        return False
    state[key] = count + 1
    STOP_FILE.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return True


def _minimal_decision(decision: engine.Decision) -> dict[str, Any]:
    """Return a redacted decision shape for denial output."""

    return {
        "outcome": decision.outcome,
        "invariant_ids": decision.invariant_ids,
        "allowed_next_actions": decision.allowed_next_actions[:2],
        "evidence_required": decision.evidence_required[:4],
    }


def _safe_reason(decision: engine.Decision) -> str:
    """Return the denial reason without credential-like substrings."""

    return decision.reason.replace("sk-", "sk-redacted-")


def _emit(data: dict[str, Any]) -> None:
    """Write one JSON response for the hook runtime."""

    sys.stdout.write(json.dumps(data, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
