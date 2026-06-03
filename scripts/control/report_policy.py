"""Report evidence checks for final, intermediate, and subagent reports."""

from __future__ import annotations

from scripts.control.principles import load_report_schema


def evaluate_report_text(text: str, *, stop_event: bool = False) -> dict[str, object]:
    """Evaluate whether a report carries required evidence markers."""
    schema = load_report_schema()
    stripped = text.strip()
    if not stripped:
        return _needs_evidence("empty report text", stop_event)
    lower = stripped.lower()
    positive_terms = [str(term) for term in schema["positive_claim_terms"]]
    positive_claim = any(term.lower() in lower for term in positive_terms)
    evidence_markers = [str(marker) for marker in schema["evidence_or_unknown_markers"]]
    has_evidence_or_unknown = any(marker.lower() in lower for marker in evidence_markers)
    matrix_markers = [str(marker) for marker in schema["required_evidence_markers"]]
    missing_matrix = [marker for marker in matrix_markers if marker not in stripped]
    if positive_claim and missing_matrix:
        return _needs_evidence("positive report lacks required evidence matrix: " + ", ".join(missing_matrix), stop_event)
    if not has_evidence_or_unknown:
        return _needs_evidence("report lacks evidence or explicit evidence absence", stop_event)
    return {"outcome": "ALLOW", "invariant_ids": ["INV-P1-001"], "reason": "report evidence requirements satisfied"}


def _needs_evidence(reason: str, stop_event: bool) -> dict[str, object]:
    """Build a report evidence finding."""
    outcome = "NEEDS_CONTINUATION" if stop_event else "NEEDS_EVIDENCE"
    return {
        "outcome": outcome,
        "invariant_ids": ["INV-P1-001"],
        "reason": reason,
        "evidence_required": ["要件照合", "基準", "証跡", "判定", "未確認事項"],
        "allowed_next_actions": ["未達または未確認を明示した報告に修正してください。"],
    }
