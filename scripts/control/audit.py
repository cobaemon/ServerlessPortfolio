"""Redacted audit writing for control decisions."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from scripts.control.principles import REPO_ROOT


AUDIT_DIR = REPO_ROOT / ".codex" / "audit"
AUDIT_FILE = AUDIT_DIR / "control_decisions.jsonl"


def redact_text(text: str) -> str:
    """Return text with common secret-looking fragments removed."""
    redacted = re.sub(r"(?i)(secret|token|password|key)=\S+", r"\1=[REDACTED]", text)
    return redacted[:500]


def write_audit_record(*, turn_id: str, actor: str, decision: Mapping[str, object], input_summary: str) -> None:
    """Append a redacted audit record without storing full prompts or secret values."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    summary = redact_text(input_summary)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "turn_id": turn_id,
        "actor": actor,
        "contract_hash": hashlib.sha256(turn_id.encode("utf-8")).hexdigest()[:16],
        "policy_version": 1,
        "invariant_ids": decision.get("invariant_ids", []),
        "decision": decision.get("outcome", "ERROR"),
        "reason": decision.get("reason", ""),
        "redacted_input_summary": summary,
        "evidence_references": [],
        "allowed_next_actions": decision.get("allowed_next_actions", []),
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
