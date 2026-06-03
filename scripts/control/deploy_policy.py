"""Deploy and AWS command checks."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping


DEPLOY_TOOLS = ("aws", "sam", "cdk", "serverless")


def is_deploy_command(command: str) -> bool:
    """Return true when the command invokes AWS or deployment tooling."""
    lower = command.strip().lower()
    return lower.startswith(DEPLOY_TOOLS) or bool(re.search(r"\b(aws|sam|cdk|serverless)\b", lower))


def evaluate_deploy(
    command: str,
    *,
    deploy_allowed: bool,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Evaluate AWS/deploy command preconditions."""
    checked_env = dict(os.environ if env is None else env)
    lower = command.lower()
    if not is_deploy_command(command):
        return {"outcome": "ALLOW", "invariant_ids": [], "reason": "not a deploy command"}
    if not deploy_allowed:
        return {
            "outcome": "DENY",
            "invariant_ids": ["INV-P1-003", "INV-P2-001"],
            "reason": "deploy or AWS command lacks explicit current-turn deploy permission",
            "allowed_next_actions": ["deploy 明示許可、profile、region、source revision 証跡を取得してください。"],
        }
    profile_ok = checked_env.get("AWS_PROFILE") == "aws_portfolio_profile" or "--profile aws_portfolio_profile" in lower
    region_ok = bool(checked_env.get("AWS_REGION") or checked_env.get("AWS_DEFAULT_REGION") or "--region " in lower)
    revision_ok = bool(checked_env.get("GUARD_SOURCE_REVISION"))
    if not (profile_ok and region_ok and revision_ok):
        missing = [
            name
            for name, ok in (
                ("AWS_PROFILE=aws_portfolio_profile", profile_ok),
                ("AWS_REGION or --region", region_ok),
                ("GUARD_SOURCE_REVISION", revision_ok),
            )
            if not ok
        ]
        return {
            "outcome": "DENY",
            "invariant_ids": ["INV-P2-001"],
            "reason": "deploy evidence is incomplete: " + ", ".join(missing),
            "allowed_next_actions": ["不足している deploy 証跡を現在ターン contract に追加してください。"],
        }
    return {"outcome": "ALLOW", "invariant_ids": ["INV-P2-001"], "reason": "deploy preconditions satisfied"}
