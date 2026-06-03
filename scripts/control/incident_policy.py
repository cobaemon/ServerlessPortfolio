"""Incident record checks."""

from __future__ import annotations

from scripts.control.principles import load_report_schema


def evaluate_incident_record_text(text: str) -> dict[str, object]:
    """Evaluate whether an incident record includes all required sections."""
    schema = load_report_schema()
    lower = text.lower()
    missing = [str(marker) for marker in schema["incident_required_markers"] if str(marker).lower() not in lower]
    if missing:
        return {
            "outcome": "DENY",
            "invariant_ids": ["INV-P1-001", "INV-P3-002"],
            "reason": "incident record lacks required markers: " + ", ".join(missing),
            "allowed_next_actions": ["record/root cause/control change/regression/remaining risk を追記してください。"],
        }
    return {"outcome": "ALLOW", "invariant_ids": ["INV-P1-001"], "reason": "incident record requirements satisfied"}
