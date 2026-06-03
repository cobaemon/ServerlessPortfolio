"""Shell command policy checks."""

from __future__ import annotations

import re
from collections.abc import Mapping

from scripts.control import asset_policy, deploy_policy, git_policy


PACKAGE_TOOLS = ("npm", "pnpm", "yarn", "pip", "apt", "apt-get", "yum", "brew", "choco")
NETWORK_TOOLS = ("curl", "wget")
WRITE_TOKENS = ("apply_patch", " tee ", " cp ", " mv ", " rm ", "new-item", "set-content", "out-file")


def evaluate_command(command: str, *, contract: object, env: Mapping[str, str] | None = None) -> dict[str, object]:
    """Evaluate a shell command against command, asset, git, and deploy policies."""
    asset_result = asset_policy.evaluate_asset_reachability(command)
    if asset_result["outcome"] == "DENY":
        return asset_result
    actor = str(getattr(contract, "actor", "unknown"))
    work_types = set(getattr(contract, "work_type", set()))
    deploy_result = deploy_policy.evaluate_deploy(
        command,
        deploy_allowed=bool(getattr(contract, "deploy_allowed", False)),
        env=env,
    )
    if deploy_result["outcome"] == "DENY":
        return deploy_result
    git_result = git_policy.evaluate_git_command(command, actor=actor)
    if git_result["outcome"] in {"DENY", "WARN"}:
        return git_result
    lower = " " + re.sub(r"\s+", " ", command.strip().lower()) + " "
    if _is_package_install(lower):
        return {
            "outcome": "DENY",
            "invariant_ids": ["INV-P2-003"],
            "reason": "external package or tool install lacks license confirmation and approval evidence",
            "allowed_next_actions": ["asset name/version/source/license/approval evidence を提示してください。"],
        }
    if any(f" {tool} " in lower for tool in NETWORK_TOOLS):
        return {
            "outcome": "DENY",
            "invariant_ids": ["INV-P3-005"],
            "reason": "network command lacks explicit trusted-source permission",
            "allowed_next_actions": ["公式サイトまたは実績ある信頼サイトの明示許可を取得してください。"],
        }
    if _is_file_write(lower) and "IMPLEMENTATION_ALLOWED" not in work_types:
        return {
            "outcome": "DENY",
            "invariant_ids": ["INV-P1-003"],
            "reason": "file write command lacks implementation permission in the current contract",
            "allowed_next_actions": ["現在ターンで file edit の明示許可を取得してください。"],
        }
    if re.search(r"\b(rm\s+-rf|remove-item\b.*-recurse)", lower):
        return {
            "outcome": "DENY",
            "invariant_ids": ["INV-P3-002"],
            "reason": "destructive recursive command is not allowed by the control policy",
            "allowed_next_actions": ["削除対象と承認を明示してください。"],
        }
    return {"outcome": "ALLOW", "invariant_ids": [], "reason": "command policy allowed"}


def _is_package_install(lower_command: str) -> bool:
    """Return true for package manager install/add commands."""
    return any(
        f" {tool} install " in lower_command or f" {tool} add " in lower_command
        for tool in PACKAGE_TOOLS
    )


def _is_file_write(lower_command: str) -> bool:
    """Return true for common shell write operations."""
    if " >" in lower_command or ">>" in lower_command:
        return True
    return any(token in lower_command for token in WRITE_TOKENS)
