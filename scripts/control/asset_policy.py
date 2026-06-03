"""Asset reachability checks for shell and tool inputs."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.control.principles import REPO_ROOT


def _deny(reason: str) -> dict[str, object]:
    """Build a denied asset finding."""
    return {
        "outcome": "DENY",
        "invariant_ids": ["INV-P2-002"],
        "reason": reason,
        "allowed_next_actions": ["明示許可された repo 内通常ファイルだけを対象にしてください。"],
    }


def _allow() -> dict[str, object]:
    """Build an allowed asset finding."""
    return {"outcome": "ALLOW", "invariant_ids": [], "reason": "asset reachability allowed"}


def has_shell_expansion(text: str) -> bool:
    """Return true when the command contains unresolved shell expansion syntax."""
    return bool(re.search(r"\$\(|`[^`]+`|\$\{[^}]+\}|%[A-Za-z_][A-Za-z0-9_]*%", text))


def has_parent_traversal(text: str) -> bool:
    """Return true when a path can traverse outside the current scope."""
    return "../" in text.replace("\\", "/")


def has_hidden_ignored_enumeration(text: str) -> bool:
    """Return true for hidden or ignored whole-tree enumeration patterns."""
    lower = text.lower()
    if "--hidden" in lower and "--no-ignore" in lower:
        return True
    if "get-childitem" in lower and "-recurse" in lower and "-force" in lower:
        return True
    return False


def has_pathless_recursive_listing(text: str) -> bool:
    """Return true for recursive listings that do not constrain allowed assets."""
    lower = text.lower()
    squashed = re.sub(r"\s+", " ", lower).strip()
    if re.search(r"\bls\b[^;\n]*-[a-z]*r[a-z]*\b", lower):
        return True
    if re.search(r"\bfind\s+\.\s+-type\s+f\b", squashed):
        return True
    if "get-childitem" in lower and "-recurse" in lower and "-force" in lower:
        return True
    return False


def has_forbidden_asset_reference(text: str) -> str | None:
    """Return a matched forbidden asset reason or None."""
    normalized = text.replace("\\", "/")
    lower = normalized.lower()
    forbidden_fragments = [
        ".git/",
        ".git config",
        ".codex/audit/",
        ".codex/state/",
        ".codex/logs/",
        "~/.aws/credentials",
        "/.aws/credentials",
        "/credentials",
        "/secrets/",
        ".env",
        "id_rsa",
        "id_ed25519",
    ]
    for fragment in forbidden_fragments:
        if fragment in lower:
            return f"forbidden asset reference: {fragment}"
    if re.search(r"\.(pem|key)(\s|$|['\"])", lower):
        return "forbidden key material reference"
    return None


def has_external_absolute_path(text: str, repo_root: Path | None = None) -> bool:
    """Return true for absolute paths outside the repository."""
    root = str(repo_root or REPO_ROOT).replace("\\", "/").lower()
    normalized = text.replace("\\", "/")
    lower = normalized.lower()
    if re.search(r"(^|\s)(/home/|/users/|/mnt/|~|\$home\b)", lower):
        return True
    for match in re.finditer(r"[a-z]:/[^\s'\"`]+", lower):
        if not match.group(0).startswith(root):
            return True
    return False


def evaluate_asset_reachability(text: str, repo_root: Path | None = None) -> dict[str, object]:
    """Evaluate whether text can reach prohibited assets."""
    if has_shell_expansion(text):
        return _deny("unresolved shell expansion can reach unknown assets")
    if has_parent_traversal(text):
        return _deny("parent traversal can reach assets outside the allowed scope")
    if has_hidden_ignored_enumeration(text):
        return _deny("hidden or ignored whole-tree enumeration is prohibited")
    if has_pathless_recursive_listing(text):
        return _deny("pathless recursive listing is prohibited")
    forbidden = has_forbidden_asset_reference(text)
    if forbidden:
        return _deny(forbidden)
    if has_external_absolute_path(text, repo_root):
        return _deny("external absolute path is prohibited")
    return _allow()
