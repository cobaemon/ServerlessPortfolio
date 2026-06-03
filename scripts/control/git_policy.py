"""Git command and Git hook checks."""

from __future__ import annotations

import re


PROTECTED_BRANCHES = {"main", "dev"}


def _actor_is_human(actor: str) -> bool:
    """Return true when local AI gates must not block the actor."""
    return actor == "human"


def evaluate_git_command(command: str, *, actor: str) -> dict[str, object]:
    """Evaluate a git shell command before execution."""
    lower = re.sub(r"\s+", " ", command.strip().lower())
    if not lower.startswith("git "):
        return {"outcome": "ALLOW", "invariant_ids": [], "reason": "not a git command"}
    if _actor_is_human(actor):
        return {
            "outcome": "WARN",
            "invariant_ids": ["INV-P1-003"],
            "reason": "human actor is not blocked by AI GitHook policy",
        }
    if lower in {"git status", "git status --short", "git diff --check"}:
        return {"outcome": "ALLOW", "invariant_ids": [], "reason": "read-only git command"}
    if lower.startswith(("git diff", "git log", "git show", "git rev-parse", "git branch --show-current")):
        return {"outcome": "ALLOW", "invariant_ids": [], "reason": "read-only git command"}
    if re.search(r"\bgit\s+(checkout|switch)\s+(-c\s+)?(main|dev)\b", lower):
        return _deny_git("AI actor cannot switch directly to protected branches")
    if re.search(r"\bgit\s+commit\b", lower):
        return _deny_git("AI actor cannot run direct git commit outside the fixed procedure")
    if re.search(r"\bgit\s+push\b", lower):
        if re.search(r"\b(main|dev)\b", lower):
            return _deny_git("AI actor cannot push directly to protected branches")
        return _deny_git("AI actor cannot push without explicit push procedure evidence")
    if re.search(r"\bgit\s+(merge|rebase|stash)\b", lower):
        return _deny_git("AI actor cannot use merge, rebase, or stash outside the fixed procedure")
    if re.search(r"\bgit\s+(checkout|switch|branch)\s+(-c\s+)?(?!codex/|v\d+\.\d+\.\d+)", lower):
        return _deny_git("AI actor cannot create or switch to non-standard branch names")
    return {"outcome": "ALLOW", "invariant_ids": [], "reason": "git command allowed"}


def evaluate_git_change(
    *,
    hook_type: str,
    actor: str,
    staged_diff: str = "",
    commit_message: str = "",
    push_refs: str = "",
) -> dict[str, object]:
    """Evaluate Git hook inputs without mutating repository state."""
    if actor in {"human", "unknown"}:
        return {
            "outcome": "WARN",
            "invariant_ids": ["INV-P1-003"],
            "reason": "local GitHook warns rather than blocks human or unknown actors",
        }
    if hook_type == "pre-commit":
        if re.search(r"(secret|token|password|private key|aws_access_key_id)", staged_diff, re.IGNORECASE):
            return _deny_git("staged diff contains possible secret material")
        return {"outcome": "ALLOW", "invariant_ids": ["INV-P3-001"], "reason": "pre-commit policy passed"}
    if hook_type == "commit-msg":
        non_empty = [line for line in commit_message.splitlines() if line.strip()]
        if len(non_empty) < 2:
            return _deny_git("commit message must contain both title and body")
        required = ("要件", "検証")
        if not all(marker in commit_message for marker in required):
            return _deny_git("commit message body must include requirement and verification evidence")
        return {"outcome": "ALLOW", "invariant_ids": ["INV-P1-001"], "reason": "commit message policy passed"}
    if hook_type == "pre-push":
        if re.search(r"refs/heads/(main|dev)\b", push_refs):
            return _deny_git("AI actor cannot push directly to protected branches")
        return {"outcome": "ALLOW", "invariant_ids": ["INV-P1-003"], "reason": "pre-push policy passed"}
    return {"outcome": "DENY", "invariant_ids": ["INV-P2-001"], "reason": f"unknown git hook type: {hook_type}"}


def _deny_git(reason: str) -> dict[str, object]:
    """Build a denied Git finding."""
    return {
        "outcome": "DENY",
        "invariant_ids": ["INV-P1-003", "INV-P2-001"],
        "reason": reason,
        "allowed_next_actions": ["branch-finalize-next または明示された Git 手順を使用してください。"],
    }
