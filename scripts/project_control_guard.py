#!/usr/bin/env python3
"""Project-wide control guard for ServerlessPortfolio.

This module is the single policy engine for Codex hooks and Git hooks.  It uses
only the Python standard library so it can run before project dependencies are
installed.  It intentionally limits hard blocks to deterministic conditions to
avoid false stops and recursive loops.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_CODEX_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "Stop",
)

CONTROL_FILES = (
    "AGENTS.md",
    ".codex/hooks.json",
    ".codex/hooks/serverless_portfolio_guard.py",
    ".codex/hooks/README.md",
    ".codex/audit/.gitignore",
    ".githooks/pre-commit",
    ".githooks/commit-msg",
    ".githooks/pre-push",
    "scripts/project_control_guard.py",
    "scripts/branch-finalize-next.ps1",
    "docs/incidents/README.md",
    "docs/ai-progress/README.md",
    "docs/development-records/README.md",
    "docs/index.md",
)

AGENTS_REQUIRED_MARKERS = (
    "人間ユーザーは AI/Codex より上位の指揮権限を持つ",
    "GitHook は CodexHook の代替ではない",
    "CodexHook は GitHook の代替ではない",
    "単一レイヤに集約してはならない",
    "誤判定・無限ループ対策",
    "GitHook 補助保証を不要扱いし",
    "固定正規手順への AI 独自判断混入は禁止する",
)

MUTATING_TOOLS = {
    "apply_patch",
    "Edit",
    "Write",
    "Bash",
    "functions.shell_command",
    "functions.apply_patch",
}

WORK_KEYWORDS = (
    "実装", "修正", "作成", "追加", "削除", "初期化", "更新", "変更", "記録",
    "検証", "実行", "デプロイ", "設計", "やり直せ", "しろ", "行え",
    "implement", "fix", "create", "add", "delete", "remove", "modify", "update",
    "record", "verify", "deploy", "run", "execute", "redesign",
)

QUESTION_PATTERNS = (
    "なぜ", "どういう状況", "説明しろ", "説明して", "報告しない", "答えない",
    "現状の説明", "質問", "why", "what happened", "status", "explain",
)

FIXED_PROCEDURE_KEYWORDS = (
    "正規手順", "固定正規手順", "固定作業", "機械的に実施", "その都度判断するな",
    "独自の判断", "勝手な判断", "指示通りに正規手順", "デプロイ指示があれば",
)

DEPLOY_PATTERNS = (
    r"\bsam\s+deploy\b",
    r"\baws\s+(cloudformation|codepipeline|lambda|s3|cloudfront|route53|iam)\b",
    r"\bterraform\s+apply\b",
)

GIT_RELEASE_PATTERNS = (
    r"\bgit\s+commit\b",
    r"\bgit\s+push\b",
    r"\bgit\s+merge\b",
    r"branch-finalize-next",
)

DESTRUCTIVE_PATTERNS = (
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bgit\s+checkout\s+--\b",
    r"\bgit\s+push\b.*\s--force",
    r"\brm\s+-rf\b",
    r"\bRemove-Item\b.*\s-Recurse\b",
)

NETWORK_ASSET_PATTERNS = (
    r"\b(npm|pnpm|yarn)\s+(install|add)\b",
    r"\bpip\s+install\b",
    r"\bInvoke-WebRequest\b",
    r"\bcurl\b",
    r"\bwget\b",
)

SECRET_PATTERNS = (
    r"auth\.json",
    r"\.env(\.|$)",
    r"credentials",
    r"id_rsa",
    r"secret",
)

FALLBACK_PATTERNS = (
    r"\|\|\s*true\b",
    r"\|\|\s*echo\b",
    r"continue-on-error:\s*true",
)


def main(argv: list[str] | None = None) -> int:
    """Run the guard as a Codex hook, Git hook, or self-test."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--pre-commit", action="store_true")
    parser.add_argument("--commit-msg")
    parser.add_argument("--pre-push", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    repo_root = repo_root_from_cwd(Path.cwd())
    if args.pre_commit:
        return git_pre_commit(repo_root)
    if args.commit_msg:
        return git_commit_msg(repo_root, Path(args.commit_msg))
    if args.pre_push:
        return git_pre_push(repo_root)
    return codex_hook(repo_root)


def codex_hook(default_root: Path) -> int:
    """Dispatch Codex hook stdin."""
    payload, parse_error = parse_json_payload(sys.stdin.read())
    repo_root = resolve_repo_root(payload, default_root)
    event_name = str(payload.get("hook_event_name", ""))

    if parse_error:
        record_event(repo_root, event_name or "ParseError", {"error": parse_error})
        return 0
    if event_name == "SessionStart":
        return codex_session_start(repo_root, payload)
    if event_name == "UserPromptSubmit":
        return codex_user_prompt_submit(repo_root, payload)
    if event_name == "PreToolUse":
        return codex_pre_tool_use(repo_root, payload)
    if event_name == "PermissionRequest":
        return codex_permission_request(repo_root, payload)
    if event_name == "PostToolUse":
        return codex_post_tool_use(repo_root, payload)
    if event_name == "Stop":
        return codex_stop(repo_root, payload)
    return 0


def codex_session_start(repo_root: Path, payload: dict[str, Any]) -> int:
    """Inject active control context at session start."""
    record_event(repo_root, "SessionStart", {"source": payload.get("source")})
    write_json(
        {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": build_runtime_context(repo_root, {}),
            },
        }
    )
    return 0


def codex_user_prompt_submit(repo_root: Path, payload: dict[str, Any]) -> int:
    """Freeze the latest user prompt as a current-turn contract."""
    prompt = str(payload.get("prompt", ""))
    contract = build_contract(prompt, payload)
    save_json(repo_root / ".codex/audit/state/current_contract.json", contract)
    record_event(repo_root, "UserPromptSubmit", {"contract": redact_contract(contract)})
    write_json(
        {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": build_runtime_context(repo_root, contract),
            },
        }
    )
    return 0


def codex_pre_tool_use(repo_root: Path, payload: dict[str, Any]) -> int:
    """Deny deterministic tool-use violations."""
    contract = load_contract(repo_root)
    tool_name = str(payload.get("tool_name", ""))
    tool_text = flatten(payload.get("tool_input"))
    reason = hard_block_reason(contract, tool_name, tool_text)
    record_event(repo_root, "PreToolUse", {"tool": tool_name, "blocked": bool(reason), "reason": reason})
    if reason:
        write_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": reason,
            }
        )
        return 0
    write_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": pre_tool_hint(contract),
            }
        }
    )
    return 0


def codex_permission_request(repo_root: Path, payload: dict[str, Any]) -> int:
    """Deny approval requests that conflict with deterministic policy."""
    contract = load_contract(repo_root)
    tool_name = str(payload.get("tool_name", ""))
    tool_text = flatten(payload.get("tool_input"))
    reason = hard_block_reason(contract, tool_name, tool_text)
    record_event(repo_root, "PermissionRequest", {"tool": tool_name, "blocked": bool(reason), "reason": reason})
    if reason:
        write_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "deny", "message": reason},
                },
                "systemMessage": reason,
            }
        )
    return 0


def codex_post_tool_use(repo_root: Path, payload: dict[str, Any]) -> int:
    """Record compact tool-result audit information."""
    record_event(
        repo_root,
        "PostToolUse",
        {
            "tool": payload.get("tool_name"),
            "input_hash": stable_hash(flatten(payload.get("tool_input"))),
            "response_hash": stable_hash(flatten(payload.get("tool_response"))),
        },
    )
    return 0


def codex_stop(repo_root: Path, payload: dict[str, Any]) -> int:
    """Block false completion once and avoid recursive stop loops."""
    if payload.get("stop_hook_active"):
        return 0
    contract = load_contract(repo_root)
    message = str(payload.get("last_assistant_message") or payload.get("message") or "")
    reason = stop_block_reason(repo_root, contract, message)
    record_event(repo_root, "Stop", {"blocked": bool(reason), "reason": reason})
    if reason:
        write_json({"decision": "block", "reason": reason})
    return 0


def git_pre_commit(repo_root: Path) -> int:
    """Validate staged content and required control files."""
    errors: list[str] = []
    errors.extend(required_control_errors(repo_root))
    errors.extend(agents_marker_errors(repo_root))
    errors.extend(hooks_json_errors(repo_root))
    errors.extend(git_hook_file_errors(repo_root))
    errors.extend(staged_diff_errors(repo_root))
    if errors:
        return fail("pre-commit control failed", errors)
    return 0


def git_commit_msg(repo_root: Path, path: Path) -> int:
    """Validate commit message structure."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return fail("commit-msg control failed", [f"cannot read commit message: {exc}"])
    lines = [line.rstrip() for line in text.splitlines()]
    nonempty = [line for line in lines if line.strip()]
    errors: list[str] = []
    if not nonempty:
        errors.append("commit message is empty")
    elif len(nonempty) < 2:
        errors.append("commit message must contain both title and body")
    elif nonempty[0] == nonempty[1]:
        errors.append("commit message body must not duplicate title")
    body = "\n".join(lines[1:]).strip()
    if body and not re.search(r"(目的|概要|理由|対応|検証|制御|実装|修正)", body):
        errors.append("commit message body must explain purpose, summary, reason, response, verification, or control")
    staged = staged_paths(repo_root)
    if any(is_control_path(path) for path in staged):
        required = ("制御系変更:", "対象:", "検証:")
        for marker in required:
            if marker not in body:
                errors.append(f"control-system commit body must include {marker}")
    if errors:
        return fail("commit-msg control failed", errors)
    return 0


def git_pre_push(repo_root: Path) -> int:
    """Protect high-risk branch pushes."""
    branch = git_output(repo_root, ["git", "branch", "--show-current"]).strip()
    stdin_text = sys.stdin.read()
    remote_refs = protected_remote_refs(stdin_text)
    errors: list[str] = []
    if branch in {"dev", "main"} and os.environ.get("AGENTS_ALLOW_PROTECTED_PUSH") != "1":
        errors.append(f"protected branch push requires AGENTS_ALLOW_PROTECTED_PUSH=1: current branch {branch}")
    if remote_refs and os.environ.get("AGENTS_ALLOW_PROTECTED_PUSH") != "1":
        errors.append("protected remote ref push requires AGENTS_ALLOW_PROTECTED_PUSH=1: " + ", ".join(remote_refs))
    if required_control_errors(repo_root):
        errors.append("required control files are missing; push is blocked")
    if errors:
        return fail("pre-push control failed", errors)
    return 0


def build_contract(prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Classify the latest user prompt into deterministic control flags."""
    prompt = repair_mojibake(prompt)
    text = normalize(prompt)
    lower = text.lower()
    explicit_work = contains_any(lower, WORK_KEYWORDS)
    question_like = contains_any(lower, QUESTION_PATTERNS)
    fixed_procedure = contains_any(lower, FIXED_PROCEDURE_KEYWORDS)
    deploy_related = contains_any(lower, ("deploy", "デプロイ", "stg", "staging", "pipeline", "aws"))
    allows_deploy = deploy_related or (fixed_procedure and contains_any(lower, ("デプロイ", "deploy", "stg", "staging")))
    return {
        "created_at": now_iso(),
        "turn_id": payload.get("turn_id"),
        "prompt_hash": stable_hash(prompt),
        "prompt": prompt,
        "explicit_work": explicit_work,
        "question_only": question_like and not explicit_work,
        "fixed_procedure_execution": fixed_procedure,
        "mentions_codex_hook": "codexhook" in lower or "codex hook" in lower or "userpromptsubmit" in lower,
        "mentions_git_hook": "githook" in lower or "git hook" in lower or ".githooks" in lower,
        "requires_comprehensive_control": contains_any(lower, ("包括", "網羅", "抜け道", "多層", "保証", "0から", "原則")),
        "allows_deploy": allows_deploy,
        "allows_git_release": allows_deploy or fixed_procedure or contains_any(lower, ("commit", "push", "merge", "branch-finalize", "正規手順")),
        "allows_destructive": contains_any(lower, ("削除", "初期化", "reset --hard", "git clean", "force push")),
        "allows_external_assets": contains_any(lower, ("install", "外部資産", "ライセンス", "npm", "pip")),
        "allows_secret_read": contains_any(lower, ("secret", "auth.json", "credentials", "秘密")),
    }


def hard_block_reason(contract: dict[str, Any], tool_name: str, tool_text: str) -> str | None:
    """Return a deterministic denial reason, or None."""
    text = normalize(tool_text)
    if is_guard_replay_command(text):
        return None
    if is_explicit_read_only_command(text) and not matches_any(text, SECRET_PATTERNS):
        return None
    command_like = is_command_tool(tool_name)
    if contract.get("question_only") and is_mutating_tool(tool_name, text):
        return "blocked: latest prompt is a question/status request, not explicit work authorization"
    if command_like and matches_any(text, DESTRUCTIVE_PATTERNS) and not contract.get("allows_destructive"):
        return "blocked: destructive operation lacks explicit current-turn authorization"
    if command_like and matches_any(text, DEPLOY_PATTERNS) and not contract.get("allows_deploy"):
        return "blocked: deploy or external environment operation lacks explicit current-turn authorization"
    if command_like and matches_any(text, GIT_RELEASE_PATTERNS) and not contract.get("allows_git_release"):
        return "blocked: commit, merge, push, or branch-finalize lacks explicit current-turn authorization"
    if command_like and matches_any(text, NETWORK_ASSET_PATTERNS) and not (
        contract.get("allows_external_assets") or contract.get("allows_deploy")
    ):
        return "blocked: external asset retrieval lacks explicit license and user authorization"
    if command_like and matches_any(text, SECRET_PATTERNS) and not contract.get("allows_secret_read"):
        return "blocked: secret or credential access lacks explicit current-turn authorization"
    if removes_control_layer(text) and not contract.get("allows_destructive"):
        return "blocked: control-layer removal lacks explicit current-turn authorization"
    return None


def stop_block_reason(repo_root: Path, contract: dict[str, Any], message: str) -> str | None:
    """Return a one-shot stop reason for false completion claims."""
    lower = normalize(message).lower()
    if not has_completion_claim(lower):
        return None
    errors = required_control_errors(repo_root) + hooks_json_errors(repo_root) + git_hook_file_errors(repo_root)
    if errors:
        return "blocked: completion claim with missing control implementation: " + "; ".join(errors[:4])
    if contract.get("requires_comprehensive_control") and not ("self-test" in lower or "検証" in lower):
        return "blocked: comprehensive control completion must report verification results"
    if contract.get("fixed_procedure_execution") and not contains_any(
        lower, ("正規手順", "branch-finalize", "stg", "検証", "承認", "拒否", "approval")
    ):
        return "blocked: fixed-procedure response must report the executed procedure or external approval denial evidence"
    if re.search(r"(agents|agants|ag\.ents).*(human|user|人間|ユーザー).*(must|制約|拘束|縛)", lower):
        return "blocked: AGENTS must not be reported as a human-user constraint"
    return None


def required_control_errors(repo_root: Path) -> list[str]:
    """Check that every required control file exists."""
    return [f"missing required control file: {path}" for path in CONTROL_FILES if not (repo_root / path).exists()]


def agents_marker_errors(repo_root: Path) -> list[str]:
    """Check that AGENTS contains required control markers."""
    path = repo_root / "AGENTS.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"cannot read AGENTS.md: {exc}"]
    return [f"AGENTS.md missing marker: {marker}" for marker in AGENTS_REQUIRED_MARKERS if marker not in text]


def hooks_json_errors(repo_root: Path) -> list[str]:
    """Validate Codex hook configuration."""
    path = repo_root / ".codex/hooks.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid .codex/hooks.json: {exc}"]
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return [".codex/hooks.json missing hooks object"]
    errors: list[str] = []
    for event in REQUIRED_CODEX_EVENTS:
        if event not in hooks:
            errors.append(f".codex/hooks.json missing event: {event}")
    content = json.dumps(data, ensure_ascii=True)
    if "project_control_guard.py" not in content:
        errors.append(".codex/hooks.json must call scripts/project_control_guard.py")
    return errors


def git_hook_file_errors(repo_root: Path) -> list[str]:
    """Validate Git hook wrappers."""
    errors: list[str] = []
    for rel_path, mode in (
        (".githooks/pre-commit", "--pre-commit"),
        (".githooks/commit-msg", "--commit-msg"),
        (".githooks/pre-push", "--pre-push"),
    ):
        path = repo_root / rel_path
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"cannot read {rel_path}: {exc}")
            continue
        if "project_control_guard.py" not in text or mode not in text:
            errors.append(f"{rel_path} must call project_control_guard.py {mode}")
    hooks_path = git_output(repo_root, ["git", "config", "--get", "core.hooksPath"]).strip()
    if hooks_path.replace("\\", "/") != ".githooks":
        errors.append("git core.hooksPath must be .githooks")
    return errors


def staged_diff_errors(repo_root: Path) -> list[str]:
    """Validate staged files and staged diff."""
    errors: list[str] = []
    staged = staged_paths(repo_root)
    deleted = staged_name_status(repo_root, "D")
    for path in deleted:
        if is_control_path(path):
            errors.append(f"staged deletion of control file is blocked: {path}")
    if any(path.startswith(".codex/audit/state/") for path in staged):
        errors.append(".codex/audit/state must not be staged")
    diff = git_output(repo_root, ["git", "diff", "--cached", "--"])
    added_diff = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    if matches_any(added_diff, FALLBACK_PATTERNS):
        errors.append("staged diff adds fallback continuation pattern")
    if staged and any(path.startswith("docs/incidents/") and path.endswith("_Incident.md") for path in staged):
        errors.extend(incident_record_errors(repo_root, staged))
    return errors


def incident_record_errors(repo_root: Path, staged: list[str]) -> list[str]:
    """Validate staged incident record minimum fields."""
    required = (
        "発生時点：",
        "本来作用すべき制御：",
        "実際に作用した制御：",
        "制御が効かなかった理由：",
        "既存再発防止策が効かなかった理由：",
        "発生前に停止できたはずのゲート：",
        "制御区分：",
        "対応策としての制御系修正：",
        "対応策としての関連ドキュメント修正：",
    )
    errors: list[str] = []
    for rel in staged:
        if not (rel.startswith("docs/incidents/") and rel.endswith("_Incident.md")):
            continue
        text = (repo_root / rel).read_text(encoding="utf-8", errors="replace")
        for marker in required:
            if marker not in text:
                errors.append(f"{rel} missing incident marker: {marker}")
    return errors


def build_runtime_context(repo_root: Path, contract: dict[str, Any]) -> str:
    """Build model-visible CodexHook context."""
    return "\n".join(
        [
            "ServerlessPortfolio comprehensive control is active.",
            "Human user authority is higher than AI/Codex.",
            "AGENTS constrains AI/Codex behavior and must not be applied as a human-user constraint.",
            "CodexHook is the primary runtime layer; GitHook is the auxiliary guarantee layer; neither replaces the other.",
            f"current_contract.explicit_work={contract.get('explicit_work')}",
            f"current_contract.question_only={contract.get('question_only')}",
            f"current_contract.requires_comprehensive_control={contract.get('requires_comprehensive_control')}",
            f"current_contract.fixed_procedure_execution={contract.get('fixed_procedure_execution')}",
            "Do not convert questions/status/fact checks into work without current explicit authorization.",
            "Do not insert AI scope judgment into fixed regular procedures.",
            "Do not report completion without verification evidence.",
        ]
    )


def pre_tool_hint(contract: dict[str, Any]) -> str:
    """Return a concise non-blocking tool-use hint."""
    if contract.get("fixed_procedure_execution"):
        return "Fixed procedure instruction detected; execute only the defined procedure and report external approval denials as blockers."
    if contract.get("explicit_work"):
        return "Tool allowed under current explicit instruction; keep scope fixed and verify before reporting."
    return "No explicit work instruction detected; avoid mutation unless user explicitly authorized work."


def parse_json_payload(raw: str) -> tuple[dict[str, Any], str | None]:
    """Parse JSON stdin."""
    raw = raw.strip()
    if not raw:
        return {}, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"{exc}; pos={exc.pos}"
    if not isinstance(value, dict):
        return {}, "payload root is not object"
    return value, None


def resolve_repo_root(payload: dict[str, Any], default_root: Path) -> Path:
    """Resolve repo root from payload cwd or default cwd."""
    cwd = Path(str(payload.get("cwd") or default_root)).resolve()
    return repo_root_from_cwd(cwd)


def repo_root_from_cwd(cwd: Path) -> Path:
    """Resolve Git root, falling back to cwd."""
    try:
        return Path(git_output(cwd, ["git", "rev-parse", "--show-toplevel"]).strip()).resolve()
    except RuntimeError:
        return cwd.resolve()


def git_output(cwd: Path, command: list[str]) -> str:
    """Run a short Git command and return stdout."""
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout


def staged_paths(repo_root: Path) -> list[str]:
    """Return staged file paths."""
    output = git_output(repo_root, ["git", "diff", "--cached", "--name-only"])
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def staged_name_status(repo_root: Path, status: str) -> list[str]:
    """Return staged paths with the requested name-status code."""
    output = git_output(repo_root, ["git", "diff", "--cached", "--name-status"])
    paths: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if parts and parts[0] == status and len(parts) > 1:
            paths.append(parts[1].replace("\\", "/"))
    return paths


def protected_remote_refs(stdin_text: str) -> list[str]:
    """Return protected remote branch names from pre-push stdin."""
    refs: list[str] = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        remote_ref = parts[2]
        if remote_ref in {"refs/heads/dev", "refs/heads/main"}:
            refs.append(remote_ref)
    return refs


def load_contract(repo_root: Path) -> dict[str, Any]:
    """Load current-turn contract."""
    try:
        value = json.loads((repo_root / ".codex/audit/state/current_contract.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_json(path: Path, value: dict[str, Any]) -> None:
    """Write JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def record_event(repo_root: Path, event: str, data: dict[str, Any]) -> None:
    """Append a compact audit event."""
    path = repo_root / ".codex/audit/state/events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {"ts": now_iso(), "event": event, "data": data}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=True, sort_keys=True) + "\n")


def flatten(value: Any) -> str:
    """Convert hook data into comparable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def normalize(text: str) -> str:
    """Normalize whitespace."""
    return re.sub(r"\s+", " ", repair_mojibake(text).replace("\u3000", " ")).strip()


def repair_mojibake(text: str) -> str:
    """Repair UTF-8 text that arrived as CP932 mojibake."""
    if not any(marker in text for marker in ("縺", "繧", "繝", "譁", "讀", "螳", "蜷", "荳", "逕", "隱", "ã", "Â")):
        return text
    for encoding, errors in (("cp932", "surrogateescape"), ("latin-1", "surrogateescape"), ("cp1252", "surrogateescape")):
        try:
            repaired = text.encode(encoding, errors=errors).decode("utf-8")
        except UnicodeError:
            continue
        if contains_any(repaired, WORK_KEYWORDS + QUESTION_PATTERNS + FIXED_PROCEDURE_KEYWORDS):
            return repaired
    return text


def contains_any(text: str, needles: tuple[str, ...]) -> bool:
    """Return whether text includes any literal needle."""
    return any(needle.lower() in text for needle in needles)


def matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Return whether text matches any regex."""
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def is_mutating_tool(tool_name: str, text: str) -> bool:
    """Return whether a tool call can mutate state."""
    if tool_name not in MUTATING_TOOLS:
        return any(token in tool_name.lower() for token in ("write", "edit", "apply_patch", "shell", "browser", "imagegen"))
    if tool_name in {"Bash", "functions.shell_command"}:
        return not is_read_only_command(text)
    return True


def is_command_tool(tool_name: str) -> bool:
    """Return whether tool input is executable shell text."""
    lower = tool_name.lower()
    return tool_name in {"Bash", "functions.shell_command"} or "shell" in lower or "bash" in lower


def is_read_only_command(text: str) -> bool:
    """Allow deterministic read-only commands."""
    return is_explicit_read_only_command(text)


def is_explicit_read_only_command(text: str) -> bool:
    """Return whether a shell command is on the explicit read-only allowlist."""
    lower = text.lower().strip()
    read_prefixes = (
        "git status", "git diff", "git show", "git config --get", "rg ", "get-content",
        "get-childitem", "test-path", "python --version", "python -m json.tool",
    )
    return any(lower.startswith(prefix) for prefix in read_prefixes)


def removes_control_layer(text: str) -> bool:
    """Detect control-layer removal attempts."""
    lower = text.lower()
    removes = ("delete file: .codex", "delete file: .githooks", "delete file: scripts/project_control_guard.py", "remove-item")
    targets = (".codex", ".githooks", "project_control_guard.py", "core.hookspath")
    return any(token in lower for token in removes) and any(target in lower for target in targets)


def is_guard_replay_command(text: str) -> bool:
    """Allow explicit hook replay verification commands that contain test payloads."""
    lower = text.lower()
    if "project_control_guard.py" not in lower or "hook_event_name" not in lower:
        return False
    if "subprocess.run" in lower or "json.dumps" in lower or "--self-test" in lower:
        return True
    return False


def is_control_path(path: str) -> bool:
    """Return whether a path is a control-system path."""
    normalized = path.replace("\\", "/")
    return any(normalized == item or normalized.startswith(item.rstrip("*")) for item in CONTROL_FILES)


def has_completion_claim(text: str) -> bool:
    """Detect completion claims."""
    return contains_any(
        text,
        ("完了", "実施しました", "実装しました", "追加しました", "修正しました", "implemented", "completed", "done"),
    )


def redact_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Remove raw prompt while keeping contract facts."""
    redacted = dict(contract)
    redacted.pop("prompt", None)
    return redacted


def stable_hash(text: str) -> str:
    """Return a short stable hash."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def now_iso() -> str:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def write_json(value: dict[str, Any]) -> None:
    """Write a JSON hook response."""
    sys.stdout.write(json.dumps(value, ensure_ascii=True, sort_keys=True))


def fail(title: str, errors: list[str]) -> int:
    """Print deterministic failure text."""
    print(title)
    for error in errors:
        print(f"- {error}")
    return 1


def run_self_test() -> int:
    """Run deterministic guard tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        create_fixture_project(root)
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=root, check=True)
        assert git_pre_commit(root) == 0

        question = build_contract("why did you not report status?", {"turn_id": "t1"})
        assert question["question_only"] is True
        assert hard_block_reason(question, "apply_patch", "*** Begin Patch\n*** Add File: a\n+a\n*** End Patch")
        mojibake = "Code hook縺ｮ讀懆ｨｼ繧定｡後▲縺ｦ"
        assert "検証を行って" in repair_mojibake(mojibake)
        assert build_contract(mojibake, {"turn_id": "t-mojibake"})["explicit_work"] is True
        incident_prompt = "インシデント記録と、再発防止策を実装しろ"
        incident_mojibake = incident_prompt.encode("utf-8").decode("cp932", errors="surrogateescape")
        assert repair_mojibake(incident_mojibake).strip() == incident_prompt
        assert build_contract(incident_mojibake, {"turn_id": "t-incident"})["explicit_work"] is True

        stg_verify = build_contract("STGでの検証を行い、検証結果の報告と採用基準を満たしているのかを報告して", {"turn_id": "t-stg"})
        assert stg_verify["explicit_work"] is True
        assert stg_verify["allows_deploy"] is True
        assert stg_verify["allows_git_release"] is True
        fixed = build_contract("STGデプロイなどの正規手順が定められている作業は、その都度判断するな。デプロイ指示があれば、指示通りに正規手順のみでデプロイする。", {"turn_id": "t-fixed"})
        assert fixed["fixed_procedure_execution"] is True
        assert fixed["allows_deploy"] is True
        assert fixed["allows_git_release"] is True
        assert hard_block_reason(fixed, "Bash", "pwsh -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\branch-finalize-next.ps1 -ConfirmExecution") is None
        assert hard_block_reason(question, "Bash", "Get-Content -Raw scripts\\branch-finalize-next.ps1") is None

        comprehensive = build_contract("CodexHookとGitHookを含む包括制御を0から実装しろ", {"turn_id": "t2"})
        assert comprehensive["explicit_work"] is True
        assert comprehensive["requires_comprehensive_control"] is True
        assert hard_block_reason(comprehensive, "Bash", "git push origin dev")
        assert hard_block_reason(comprehensive, "Bash", "subprocess.run(['python','scripts/project_control_guard.py'], input=json.dumps({'hook_event_name':'PermissionRequest','tool_input':{'command':'git push origin dev'}}))") is None
        assert hard_block_reason(comprehensive, "Bash", "git status --short") is None
        assert protected_remote_refs("refs/heads/v1 123 refs/heads/dev 456") == ["refs/heads/dev"]

        save_json(root / ".codex/audit/state/current_contract.json", comprehensive)
        assert stop_block_reason(root, comprehensive, "実装しました。")
        assert stop_block_reason(root, comprehensive, "実装しました。self-test と検証を実施しました。") is None

        msg = root / "msg.txt"
        msg.write_text("制御を実装\n\n目的: 多層制御を実装\n検証: self-test\n", encoding="utf-8")
        assert git_commit_msg(root, msg) == 0
    print("project_control_guard self-test passed")
    return 0


def create_fixture_project(root: Path) -> None:
    """Create a minimal valid fixture project for self-test."""
    for rel in CONTROL_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("\n".join(AGENTS_REQUIRED_MARKERS), encoding="utf-8")
    hooks = {"hooks": {event: [{"hooks": [{"type": "command", "command": "python scripts/project_control_guard.py"}]}] for event in REQUIRED_CODEX_EVENTS}}
    (root / ".codex/hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
    (root / ".githooks/pre-commit").write_text("python scripts/project_control_guard.py --pre-commit\n", encoding="utf-8")
    (root / ".githooks/commit-msg").write_text("python scripts/project_control_guard.py --commit-msg \"$1\"\n", encoding="utf-8")
    (root / ".githooks/pre-push").write_text("python scripts/project_control_guard.py --pre-push\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
