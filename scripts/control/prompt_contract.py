"""Current-turn contract classification."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from scripts.control.principles import load_assets


def classify_prompt_data(prompt: str, *, actor: str, env: Mapping[str, str] | None = None) -> dict[str, object]:
    """Classify a user prompt into the current-turn contract fields."""
    normalized = prompt.strip()
    lower = normalized.lower()
    work_types: set[str] = set()
    if any(word in normalized for word in ("実装", "修正", "変更", "追加", "作成しろ", "実装しろ")) or "implement" in lower:
        work_types.add("IMPLEMENTATION_ALLOWED")
    if "正式な設計書" in normalized or "設計書を作成" in normalized:
        work_types.add("DESIGN_DOCUMENT_ALLOWED")
    if any(word in normalized for word in ("レビュー", "review")):
        work_types.add("REVIEW_ONLY")
    if any(word in normalized for word in ("計画", "plan")) and "IMPLEMENTATION_ALLOWED" not in work_types:
        work_types.add("PLAN_ONLY")
    if any(word in normalized for word in ("報告", "status", "状況")) and not work_types:
        work_types.add("REPORT_ONLY")
    if any(word in lower for word in ("deploy", "staging", "production")) or any(word in normalized for word in ("デプロイ", "本番", "ステージング")):
        if any(word in normalized for word in ("許可", "実行", "しろ", "して")) or "deploy" in lower:
            work_types.add("DEPLOY_ALLOWED")
    if not work_types:
        work_types.add("UNKNOWN_HIGH_RISK")
    ambiguity_items: list[str] = []
    if "UNKNOWN_HIGH_RISK" in work_types:
        ambiguity_items.append("作業種別が明示されていない")
    assets = load_assets()
    turn_id = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return {
        "turn_id": turn_id,
        "actor": actor,
        "work_type": sorted(work_types),
        "explicit_instructions": [normalized] if normalized else [],
        "obligations": [
            "事実のみ報告する",
            "すべての報告に evidence または evidence 不在を明示する",
            "設計書と要件に従う",
        ],
        "acceptance_criteria": ["docs/comprehensive-control-design-formal.md の受け入れ基準"],
        "ambiguity_items": ambiguity_items,
        "allowed_assets": assets["allowed_assets"],
        "prohibited_assets": assets["prohibited_assets"],
        "allowed_tools": [],
        "prohibited_tools": [],
        "deploy_allowed": "DEPLOY_ALLOWED" in work_types,
        "evidence_requirements": ["要件照合", "判定基準", "実施内容", "証跡", "未確認事項"],
    }
