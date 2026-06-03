"""Codex hook adapter that delegates every event to scripts.control.policy_engine."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.control import audit, policy_engine  # noqa: E402

STATE_FILE = REPO_ROOT / ".codex" / "state" / "stop_continuations.json"


def main() -> int:
    """Read hook input, evaluate it, and emit Codex-compatible JSON output."""
    payload = _read_payload()
    event = str(payload.get("hook_event_name") or payload.get("event") or "")
    actor = policy_engine._actor(os.environ.get("GUARD_ACTOR", "unknown"))
    contract = _contract_from_payload(payload, actor)
    if event == "UserPromptSubmit":
        _emit({"decision": "continue", "contract": contract.to_json_dict(), "context": _contract_context(contract)})
        return 0
    if event == "PreToolUse":
        decision = policy_engine.evaluate_tool_use(contract, str(payload.get("tool_name", "")), _dict(payload.get("tool_input")))
        _audit(contract, decision, event)
        return _emit_tool_decision(decision)
    if event == "PermissionRequest":
        decision = policy_engine.evaluate_permission_request(contract, payload)
        _audit(contract, decision, event)
        return _emit_tool_decision(decision)
    if event == "PostToolUse":
        decision = policy_engine.evaluate_tool_result(
            contract,
            str(payload.get("tool_name", "")),
            _dict(payload.get("tool_input")),
            _dict(payload.get("tool_result")),
        )
        _audit(contract, decision, event)
        _emit({"decision": "continue", "policy": decision.to_json_dict()})
        return 0
    if event in {"Stop", "SubagentStop"}:
        text = _report_text(payload)
        decision = policy_engine.evaluate_report(contract, text, stop_event=True)
        _audit(contract, decision, event)
        return _emit_stop_decision(contract, decision)
    _emit({"decision": "continue", "contract": contract.to_json_dict()})
    return 0


def _read_payload() -> dict[str, Any]:
    """Return JSON hook payload, or an empty payload if stdin is empty."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"hook_event_name": "Unknown", "raw_input": raw[:200]}
    return parsed if isinstance(parsed, dict) else {"hook_event_name": "Unknown", "raw_input": raw[:200]}


def _contract_from_payload(payload: dict[str, Any], actor: policy_engine.Actor) -> policy_engine.Contract:
    """Build a current-turn contract from payload or environment prompt text."""
    prompt = str(
        payload.get("prompt")
        or payload.get("user_prompt")
        or payload.get("message")
        or os.environ.get("GUARD_USER_PROMPT")
        or ""
    )
    return policy_engine.classify_prompt(prompt, policy_engine.RuntimeContext(actor=actor, env=os.environ))


def _dict(value: Any) -> dict[str, object]:
    """Return value as a dict when the hook input shape provides one."""
    return value if isinstance(value, dict) else {}


def _report_text(payload: dict[str, Any]) -> str:
    """Extract report text from known Stop/SubagentStop payload fields."""
    for key in ("response", "final_response", "message", "subagent_response"):
        if payload.get(key):
            return str(payload[key])
    return ""


def _contract_context(contract: policy_engine.Contract) -> str:
    """Return compact developer context for UserPromptSubmit."""
    return (
        "Current-turn contract: "
        f"work_type={sorted(contract.work_type)}; "
        f"ambiguity_items={contract.ambiguity_items}; "
        "reports require evidence or explicit evidence absence."
    )


def _emit_tool_decision(decision: policy_engine.Decision) -> int:
    """Emit PreToolUse/PermissionRequest hook-specific decision output."""
    if decision.outcome == "DENY":
        _emit(
            {
                "permissionDecision": "deny",
                "permissionDecisionReason": decision.reason,
                "policy": decision.to_json_dict(),
            }
        )
        return 0
    _emit({"permissionDecision": "allow", "policy": decision.to_json_dict()})
    return 0


def _emit_stop_decision(contract: policy_engine.Contract, decision: policy_engine.Decision) -> int:
    """Emit Stop output while limiting continuation loops."""
    if decision.outcome == "NEEDS_CONTINUATION" and _consume_stop_continuation(contract, decision):
        _emit({"decision": "block", "reason": decision.reason, "policy": decision.to_json_dict()})
        return 0
    _emit({"decision": "continue", "policy": decision.to_json_dict()})
    return 0


def _consume_stop_continuation(contract: policy_engine.Contract, decision: policy_engine.Decision) -> bool:
    """Return true only for the first same turn + invariant + reason continuation."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    key_text = contract.turn_id + "|" + ",".join(decision.invariant_ids) + "|" + decision.reason
    key = hashlib.sha256(key_text.encode("utf-8")).hexdigest()
    state: dict[str, int] = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    count = int(state.get(key, 0))
    if count >= 1:
        return False
    state[key] = count + 1
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return True


def _audit(contract: policy_engine.Contract, decision: policy_engine.Decision, event: str) -> None:
    """Write redacted hook audit evidence."""
    audit.write_audit_record(
        turn_id=contract.turn_id,
        actor=contract.actor,
        decision=decision.to_json_dict(),
        input_summary=event,
    )


def _emit(data: dict[str, object]) -> None:
    """Write one JSON response for the hook runtime."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
