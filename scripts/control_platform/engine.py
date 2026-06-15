"""Policy-as-code engine for Control Platform v2.

The engine is dependency-free and intentionally category-based. It maps
commands, prompts, reports, Git hook inputs, and manifest files to invariant
decisions without incident-ID-specific branches.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import re
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = REPO_ROOT / "controls" / "policy.json"


@dataclass(frozen=True)
class Contract:
    """Current-turn contract inferred from explicit user instruction."""

    work_type: str
    flags: list[str] = field(default_factory=list)
    turn_hash: str = ""
    fixed_procedure: bool = False
    performance_experiment: bool = False
    environment_mutation_allowed: bool = False
    explicit_measurement_procedure: bool = False
    ambiguities: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable contract."""

        return asdict(self)


@dataclass(frozen=True)
class Decision:
    """Policy decision returned by all control surfaces."""

    outcome: str
    invariant_ids: list[str]
    reason: str
    allowed_next_actions: list[str] = field(default_factory=list)
    evidence_required: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable decision."""

        return asdict(self)


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    """Load the policy JSON source of truth."""

    return json.loads(path.read_text(encoding="utf-8"))


def _hash_text(text: str) -> str:
    """Return a short hash for correlation without logging full content."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_actor(raw_actor: str | None) -> str:
    """Normalize actor values to the policy actor model."""

    actor = (raw_actor or "").strip().lower()
    if actor in {"codex", "ai"}:
        return "codex"
    if actor in {"ci", "codebuild", "github-actions"}:
        return "ci"
    if actor == "human":
        return "human"
    return "unknown"


def actor_from_environment(env: dict[str, str] | None = None) -> str:
    """Infer actor from environment variables for GitHook and CLI use."""

    values = env or os.environ
    explicit = values.get("GUARD_ACTOR")
    if explicit:
        return normalize_actor(explicit)
    if values.get("CI") or values.get("CODEBUILD_BUILD_ID"):
        return "ci"
    return "human"


def _decision_for_policy_error(exc: Exception, actor: str) -> Decision:
    """Fail closed for AI/CI and warn-only for human actor on policy errors."""

    if normalize_actor(actor) == "human":
        return Decision(
            "WARN",
            ["INV-P1-PERMISSION"],
            f"Policy could not be read; human actor is warn-only: {type(exc).__name__}.",
            ["Repair controls/policy.json before relying on AI/CI enforcement."],
            ["policy parse evidence"],
        )
    return Decision(
        "ERROR",
        ["INV-P1-PERMISSION"],
        f"Policy could not be read; strict actor fails closed: {type(exc).__name__}.",
        ["Repair controls/policy.json before continuing."],
        ["policy parse evidence"],
    )


def _contains_all(text: str, terms: list[str]) -> bool:
    """Return true when every term is present case-insensitively."""

    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def _has_any(text: str, terms: list[str]) -> bool:
    """Return true when any term is present case-insensitively."""

    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _has_completion_claim(text: str, terms: list[str]) -> bool:
    """Return true for positive completion claims, excluding explicit incompletion."""

    scrubbed = text
    for marker in ("完了不可", "未完了", "完了可否: 不可", "完了可否: 未完了", "完了できません"):
        scrubbed = scrubbed.replace(marker, "")
    return _has_any(scrubbed, terms)


def _contract_allows_implementation(contract: Contract) -> bool:
    """Return whether file edits are permitted by the current contract."""

    return contract.work_type in {
        "IMPLEMENTATION_ALLOWED",
        "CONTROL_DESIGN",
        "INCIDENT_RESPONSE",
    }


def classify_prompt(prompt: str) -> Contract:
    """Classify current-turn text into a conservative contract.

    The classifier uses explicit terms and does not carry permission from older
    turns. It assigns one primary work type plus flags for cross-cutting planes.
    """

    text = prompt or ""
    flags: list[str] = []
    lowered = text.lower()
    turn_hash = _hash_text(text)

    deploy_target = bool(re.search(r"\b(STG|staging|PROD|prod|production)\b|ステージング|本番", text, re.IGNORECASE))
    deploy_action = bool(
        re.search(
            r"デプロイ|deploy|反映して|反映しろ|反映せよ|反映する|反映を行|反映を実施|反映させ",
            text,
            re.IGNORECASE,
        )
    )
    deploy = deploy_target and deploy_action
    fixed = deploy or "固定正規手順" in text or "closed procedure" in lowered
    perf = bool(
        re.search(
            r"性能|速度|体感|表示|ブラウザ|ユーザー視点|ユーザ視点|cold|cold-like|初回起動|FCP|LCP|DOMContentLoaded|Navigation",
            text,
            re.IGNORECASE,
        )
    )
    env_mutation = bool(
        re.search(
            r"update-alias|publish-version|update-function-configuration|alias|CloudFormation|CodePipeline|環境変異|Lambda",
            text,
            re.IGNORECASE,
        )
    )
    incident = "インシデント" in text or ("原因" in text and "再発" in text)
    control_design = "Control Platform" in text or "制御" in text or "policy-as-code" in lowered
    review = "レビュー" in text or "review" in lowered
    plan = "計画" in text or "plan" in lowered
    verify = "検証" in text or "verify" in lowered
    report = "報告" in text or "report" in lowered
    implementation = bool(re.search(r"実装|作成|更新|修正|変更|移植|オーバーホール|overhaul", text, re.IGNORECASE))
    question = bool(re.search(r"なぜ|理由|説明|教えて|確認して|どうして|\?", text)) and not implementation

    if fixed:
        flags.append("FIXED_PROCEDURE_BOUND")
    if perf:
        flags.append("PERFORMANCE_EXPERIMENT")
    if env_mutation:
        flags.append("ENVIRONMENT_MUTATION")
    if "SnapStart" in text or "cold" in lowered or "初回起動" in text:
        flags.append("COLD_START_VERIFICATION")
    if incident:
        flags.append("INCIDENT_RESPONSE")
    if control_design:
        flags.append("CONTROL_DESIGN")

    if deploy:
        work_type = "DEPLOY_ALLOWED"
    elif incident:
        work_type = "INCIDENT_RESPONSE" if implementation else "REPORT_ONLY"
    elif control_design and implementation:
        work_type = "CONTROL_DESIGN"
    elif perf and not implementation:
        work_type = "PERFORMANCE_EXPERIMENT"
    elif review and not implementation:
        work_type = "REVIEW_ONLY"
    elif plan and not implementation:
        work_type = "PLAN_ONLY"
    elif verify and not implementation:
        work_type = "VERIFY_ONLY"
    elif report and not implementation:
        work_type = "REPORT_ONLY"
    elif question:
        work_type = "QUESTION_ONLY"
    elif implementation:
        work_type = "IMPLEMENTATION_ALLOWED"
    else:
        work_type = "QUESTION_ONLY"

    return Contract(
        work_type=work_type,
        flags=sorted(set(flags)),
        turn_hash=turn_hash,
        fixed_procedure=fixed,
        performance_experiment=perf,
        environment_mutation_allowed=deploy,
        explicit_measurement_procedure="明示測定手順" in text or "explicit measurement procedure" in lowered,
    )


def validate_policy(path: Path = DEFAULT_POLICY_PATH) -> Decision:
    """Validate policy schema fields and required invariant/work-type entries."""

    try:
        policy = load_policy(path)
    except Exception as exc:  # pragma: no cover - type captured in decision.
        return _decision_for_policy_error(exc, "codex")

    required_keys = {
        "version",
        "schema_version",
        "principles",
        "actors",
        "work_types",
        "invariants",
        "forbidden_asset_patterns",
        "forbidden_command_patterns",
        "report_gate",
        "deploy_report_gate",
    }
    missing = sorted(required_keys.difference(policy))
    required_work_types = {
        "QUESTION_ONLY",
        "PLAN_ONLY",
        "REVIEW_ONLY",
        "IMPLEMENTATION_ALLOWED",
        "VERIFY_ONLY",
        "DEPLOY_ALLOWED",
        "FIXED_PROCEDURE_BOUND",
        "PERFORMANCE_EXPERIMENT",
        "ENVIRONMENT_MUTATION",
        "COLD_START_VERIFICATION",
        "INCIDENT_RESPONSE",
        "CONTROL_DESIGN",
        "REPORT_ONLY",
    }
    missing_work_types = sorted(required_work_types.difference(set(policy.get("work_types", []))))
    invariant_ids = {item.get("id") for item in policy.get("invariants", [])}
    required_invariants = {
        "INV-P1-EVIDENCE",
        "INV-P1-PERMISSION",
        "INV-ASSET-REACHABILITY",
        "INV-CONTRACT-SCOPE",
        "INV-FIXED-PROCEDURE",
        "INV-PERF-LAYER",
        "INV-ENV-MUTATION",
        "INV-SNAPSTART-READY",
        "INV-REPORT-GATE",
        "INV-DEPLOY-AWS-CONFIRMATION",
        "INV-INCIDENT-LIFECYCLE",
        "INV-HUMAN-NONBLOCKING",
    }
    missing_invariants = sorted(required_invariants.difference(invariant_ids))
    if missing or missing_work_types or missing_invariants:
        return Decision(
            "DENY",
            ["INV-REPORT-GATE"],
            "Policy schema is incomplete.",
            ["Restore required policy fields before relying on controls."],
            missing + missing_work_types + missing_invariants,
        )
    return Decision("ALLOW", [], "Policy schema validates.", [], [])


def _protected_asset_decision(command: str, policy: dict[str, Any]) -> Decision | None:
    """Return a reachability denial when a command targets protected assets."""

    normalized = command.replace("\\", "/")
    for group in policy.get("forbidden_asset_patterns", []):
        for pattern in group.get("patterns", []):
            marker = pattern.replace("\\", "/")
            if marker and marker.lower() in normalized.lower():
                return Decision(
                    "DENY",
                    [group.get("invariant", "INV-ASSET-REACHABILITY")],
                    f"Command can reach forbidden asset category {group.get('id', 'unknown')}.",
                    ["Use an explicit allowed repository path."],
                    ["allowed path scope"],
                )
    if "$(" in command or "`" in command or "${" in command:
        return Decision(
            "DENY",
            ["INV-ASSET-REACHABILITY"],
            "Command contains shell expansion that can bypass explicit path review.",
            ["Use literal command arguments with explicit repository paths."],
            ["expanded path evidence"],
        )
    return None


def evaluate_command(command: str, contract: Contract | None = None, actor: str = "codex") -> Decision:
    """Evaluate a command before execution."""

    actor = normalize_actor(actor)
    try:
        policy = load_policy()
    except Exception as exc:
        return _decision_for_policy_error(exc, actor)

    contract = contract or Contract("QUESTION_ONLY", turn_hash=_hash_text(""))
    command_text = command or ""
    lowered = command_text.lower()

    protected = _protected_asset_decision(command_text, policy)
    if protected:
        return protected if actor != "human" else _human_warn(protected)

    for pattern in policy.get("forbidden_command_patterns", []):
        if _contains_all(command_text, pattern.get("all_terms", [])):
            decision = Decision(
                "DENY",
                [pattern.get("invariant", "INV-ASSET-REACHABILITY")],
                f"Forbidden broad or hidden enumeration pattern {pattern.get('id')}.",
                ["Search explicit project paths without hidden/ignored whole-tree enumeration."],
                ["explicit target path"],
            )
            return decision if actor != "human" else _human_warn(decision)

    if "get-childitem" in lowered and "-recurse" in lowered and "-path" not in lowered and "-literalpath" not in lowered:
        decision = Decision(
            "DENY",
            ["INV-ASSET-REACHABILITY"],
            "Pathless recursive listing is forbidden.",
            ["Use explicit bounded paths."],
            ["bounded path evidence"],
        )
        return decision if actor != "human" else _human_warn(decision)

    for marker in policy.get("external_install_commands", []):
        if marker in lowered:
            decision = Decision(
                "DENY",
                ["INV-P1-PERMISSION"],
                "External package or tool installation is outside the permitted local control implementation scope.",
                ["Use existing standard-library or repository-local assets only."],
                ["license and install permission"],
            )
            return decision if actor != "human" else _human_warn(decision)

    file_write_markers = ["apply_patch", "writefile", "set-content", "out-file", "new-item -itemtype file"]
    if any(marker in lowered for marker in file_write_markers) and not _contract_allows_implementation(contract):
        decision = Decision(
            "DENY",
            ["INV-CONTRACT-SCOPE", "INV-P1-PERMISSION"],
            f"{contract.work_type} does not permit file creation or edit.",
            ["Ask for explicit implementation permission or restrict the action to reporting."],
            ["current-turn permission"],
        )
        return decision if actor != "human" else _human_warn(decision)

    for cmd in policy.get("deploy_and_push_commands", []):
        if cmd in lowered:
            if cmd == "git push":
                decision = Decision(
                    "DENY",
                    ["INV-P1-PERMISSION"],
                    "Git push is not allowed without explicit current-turn push permission.",
                    ["Stop before push and report the missing permission."],
                    ["current-turn push permission"],
                )
                return decision if actor != "human" else _human_warn(decision)
            if contract.work_type != "DEPLOY_ALLOWED":
                decision = Decision(
                    "DENY",
                    ["INV-P1-PERMISSION", "INV-ENV-MUTATION"],
                    "Deploy command is not allowed by the current-turn contract.",
                    ["Request explicit deploy permission and fixed procedure evidence."],
                    ["deploy contract", "fixed procedure"],
                )
                return decision if actor != "human" else _human_warn(decision)

    for cmd in policy.get("aws_environment_mutation_commands", []):
        if cmd in lowered:
            allowed_deploy = contract.work_type == "DEPLOY_ALLOWED" and contract.fixed_procedure
            allowed_measurement = contract.explicit_measurement_procedure and contract.environment_mutation_allowed
            if allowed_deploy or allowed_measurement:
                return Decision(
                    "ALLOW",
                    ["INV-FIXED-PROCEDURE" if allowed_deploy else "INV-ENV-MUTATION"],
                    "Environment mutation is inside an explicit procedure.",
                    [],
                    ["procedure evidence", "rollback evidence"],
                )
            decision = Decision(
                "DENY",
                ["INV-ENV-MUTATION"],
                "STG/prod environment mutation requires fixed deploy or explicit measurement procedure.",
                ["Create or retrieve an explicit procedure before mutation."],
                ["procedure", "rollback", "readiness gates"],
            )
            return decision if actor != "human" else _human_warn(decision)

    if "update-alias" in lowered and "live" in lowered and contract.performance_experiment:
        decision = Decision(
            "DENY",
            ["INV-ENV-MUTATION", "INV-SNAPSTART-READY"],
            "Direct live alias switching for measurement is prohibited without an explicit procedure.",
            ["Use fixed deploy or safe measurement procedure with readiness gates."],
            ["SnapStart state", "rollback", "API Gateway 5XX monitoring"],
        )
        return decision if actor != "human" else _human_warn(decision)

    return Decision("ALLOW", [], "No blocking invariant matched.", [], [])


def _human_warn(decision: Decision) -> Decision:
    """Convert AI-only blocking decisions to warn-only for human actor."""

    return Decision(
        "WARN",
        ["INV-HUMAN-NONBLOCKING", *decision.invariant_ids],
        f"Human actor warn-only: {decision.reason}",
        decision.allowed_next_actions,
        decision.evidence_required,
    )


def evaluate_tool_use(
    contract: Contract,
    tool_name: str,
    tool_input: dict[str, Any],
    actor: str = "codex",
) -> Decision:
    """Evaluate a tool call before execution."""

    text = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    lowered_tool = (tool_name or "").lower()
    if any(marker in lowered_tool for marker in ("apply_patch", "edit", "write")) and not _contract_allows_implementation(contract):
        decision = Decision(
            "DENY",
            ["INV-CONTRACT-SCOPE", "INV-P1-PERMISSION"],
            f"{contract.work_type} does not permit file edits.",
            ["Ask for explicit implementation permission or provide a report only."],
            ["current-turn permission"],
        )
        return decision if normalize_actor(actor) != "human" else _human_warn(decision)
    command = str(tool_input.get("command") or tool_input.get("cmd") or text)
    return evaluate_command(command, contract, actor)


def evaluate_permission_request(contract: Contract, payload: dict[str, Any], actor: str = "codex") -> Decision:
    """Evaluate a permission escalation request before it can run."""

    return evaluate_tool_use(contract, str(payload.get("tool_name", "")), payload, actor)


def evaluate_tool_result(tool_result: dict[str, Any], actor: str = "codex") -> Decision:
    """Evaluate a tool result for escaped protected data indicators."""

    try:
        policy = load_policy()
    except Exception as exc:
        return _decision_for_policy_error(exc, actor)
    text = json.dumps(tool_result, ensure_ascii=False, sort_keys=True)
    protected = _protected_asset_decision(text, policy)
    if protected:
        return protected if normalize_actor(actor) != "human" else _human_warn(protected)
    if re.search(r"sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,}", text):
        decision = Decision(
            "DENY",
            ["INV-ASSET-REACHABILITY"],
            "Tool result appears to contain a credential-like value.",
            ["Stop and report only that a secret-like value was exposed."],
            ["redacted incident evidence"],
        )
        return decision if normalize_actor(actor) != "human" else _human_warn(decision)
    return Decision("ALLOW", [], "Tool result passes post-use checks.", [], [])


def evaluate_report(report: str, contract: Contract | None = None, actor: str = "codex") -> Decision:
    """Evaluate final or intermediate report text before output."""

    try:
        policy = load_policy()
    except Exception as exc:
        return _decision_for_policy_error(exc, actor)
    text = report or ""
    contract = contract or Contract("QUESTION_ONLY", turn_hash=_hash_text(""))
    gate = policy.get("report_gate", {})

    if contract.fixed_procedure and _has_any(text, policy.get("fixed_procedure_forbidden_stop_markers", [])):
        if not _has_any(text, policy.get("fixed_procedure_allowed_hard_stop_markers", [])):
            return Decision(
                "DENY_STOP_CONTINUE_PROCEDURE",
                ["INV-FIXED-PROCEDURE"],
                "Report attempts to stop a closed procedure using a forbidden stop predicate.",
                ["Continue the next fixed procedure step unless an allowed hard stop predicate exists."],
                ["allowed hard stop predicate evidence"],
            )

    perf = policy.get("performance", {})
    browser_claim = _has_any(text, perf.get("browser_claim_terms", []))
    browser_evidence = _has_any(text, perf.get("browser_evidence_terms", []))
    server_only = _has_any(text, perf.get("server_only_terms", []))
    if browser_claim and not browser_evidence:
        return Decision(
            "NEEDS_EVIDENCE",
            ["INV-PERF-LAYER", "INV-P1-EVIDENCE"],
            "Browser or user-visible performance claim lacks browser evidence or explicit unmeasured disclosure.",
            ["Provide browser_navigation/browser_paint evidence or mark it unmeasured."],
            perf.get("browser_evidence_terms", []),
        )
    if browser_claim and server_only and not browser_evidence:
        return Decision(
            "NEEDS_EVIDENCE",
            ["INV-PERF-LAYER"],
            "CloudWatch or curl-only evidence cannot support browser/user-visible performance claims.",
            ["Separate server/HTTP evidence from browser/user-visible claims."],
            ["browser_navigation", "browser_paint", "未測定"],
        )

    cold_claim = _has_any(text, perf.get("cold_claim_terms", []))
    if cold_claim and _has_any(text, perf.get("cold_forbidden_markers", [])):
        return Decision(
            "NEEDS_EVIDENCE",
            ["INV-PERF-LAYER", "INV-SNAPSTART-READY"],
            "Cold-like first request claim uses recovery, warm, or stabilized sample markers.",
            ["Reclassify the sample or provide valid cold-like evidence."],
            ["State=Active", "SnapStart.OptimizationStatus=On", "no 5XX before sample"],
        )

    if "SnapStart" in text and ("測定" in text or "改善" in text or "検証済み" in text):
        missing_snapstart = [term for term in perf.get("snapstart_required_terms", []) if term not in text]
        if missing_snapstart:
            return Decision(
                "NEEDS_EVIDENCE",
                ["INV-SNAPSTART-READY"],
                "SnapStart measurement claim lacks readiness evidence.",
                ["Add SnapStart readiness evidence or mark it unverified."],
                missing_snapstart,
            )

    if _has_completion_claim(text, gate.get("completion_terms", [])):
        required_sections = gate.get("required_sections", [])
        required_columns = gate.get("required_matrix_columns", [])
        missing = [item for item in [*required_sections, *required_columns] if item not in text]
        if missing:
            return Decision(
                "NEEDS_EVIDENCE",
                ["INV-REPORT-GATE", "INV-P1-EVIDENCE"],
                "Completion-like report is missing required evidence matrix fields.",
                ["Add requirement/evidence/judgment/unknown matrix or remove completion claim."],
                missing,
            )

    deploy_gate = policy.get("deploy_report_gate", {})
    if contract.work_type == "DEPLOY_ALLOWED" and _has_completion_claim(
        text,
        deploy_gate.get("completion_terms", gate.get("completion_terms", [])),
    ):
        # Deploy completion reports must carry AWS-side confirmation evidence.
        missing_deploy = [term for term in deploy_gate.get("aws_confirmation_terms", []) if term not in text]
        if missing_deploy:
            return Decision(
                "NEEDS_EVIDENCE",
                ["INV-DEPLOY-AWS-CONFIRMATION", "INV-P1-EVIDENCE"],
                "Deploy completion claim lacks required AWS confirmation evidence.",
                ["Add CodePipeline, CloudFormation, and Lambda evidence or mark deploy confirmation incomplete."],
                missing_deploy,
            )

    if _has_any(text, gate.get("incident_completion_terms", [])):
        missing_incident = [term for term in gate.get("incident_required_terms", []) if term not in text]
        if missing_incident:
            return Decision(
                "NEEDS_EVIDENCE",
                ["INV-INCIDENT-LIFECYCLE"],
                "Incident recurrence-prevention claim lacks lifecycle evidence.",
                ["Add the full incident lifecycle evidence or mark prevention incomplete."],
                missing_incident,
            )

    return Decision("ALLOW", [], "Report passes policy gates.", [], [])


def validate_hooks(path: Path | None = None) -> Decision:
    """Validate that Codex hooks connect required events to the v2 adapter."""

    hooks_path = path or (REPO_ROOT / ".codex" / "hooks.json")
    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        policy = load_policy()
    except Exception as exc:
        return _decision_for_policy_error(exc, "codex")
    hooks = data.get("hooks", {})
    missing_events = [event for event in policy["required_hook_events"] if event not in hooks]
    adapter_missing: list[str] = []
    timeout_errors: list[str] = []
    for event, entries in hooks.items():
        for entry in entries:
            if event in {"PreToolUse", "PermissionRequest", "PostToolUse"} and "matcher" not in entry:
                adapter_missing.append(f"{event}:matcher")
            for hook in entry.get("hooks", []):
                command = str(hook.get("command", ""))
                timeout = int(hook.get("timeout", 0))
                if "scripts/control_platform/codex_hook_adapter.py" not in command.replace("\\", "/"):
                    adapter_missing.append(f"{event}:adapter")
                if timeout <= 0 or timeout > 10:
                    timeout_errors.append(f"{event}:timeout={timeout}")
    if missing_events or adapter_missing or timeout_errors:
        return Decision(
            "DENY",
            ["INV-REPORT-GATE"],
            "Codex hooks are not fully connected to the v2 adapter.",
            ["Update .codex/hooks.json to call scripts/control_platform/codex_hook_adapter.py."],
            missing_events + adapter_missing + timeout_errors,
        )
    return Decision("ALLOW", [], "Codex hooks validate.", [], [])


def validate_githooks() -> Decision:
    """Validate GitHook files and their v2 policy engine connection."""

    missing: list[str] = []
    for name in ("pre-commit", "commit-msg", "pre-push"):
        path = REPO_ROOT / ".githooks" / name
        if not path.exists():
            missing.append(name)
            continue
        text = path.read_text(encoding="utf-8")
        if "scripts.control_platform.cli" not in text:
            missing.append(f"{name}:engine")
    if missing:
        return Decision(
            "DENY",
            ["INV-REPORT-GATE"],
            "GitHook files are missing or not connected to the v2 CLI.",
            ["Update .githooks/pre-commit, commit-msg, and pre-push."],
            missing,
        )
    return Decision("ALLOW", [], "GitHooks validate.", [], [])


def validate_rag_sources(path: Path | None = None) -> Decision:
    """Validate the local RAG source manifest and registered paths."""

    manifest_path = path or (REPO_ROOT / "controls" / "rag_sources.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        policy = load_policy()
    except Exception as exc:
        return _decision_for_policy_error(exc, "codex")
    required = set(policy.get("source_manifest_required_fields", []))
    missing: list[str] = []
    for source in manifest.get("sources", []):
        fields = set(source)
        absent = sorted(required.difference(fields))
        if absent:
            missing.append(f"{source.get('source_id', 'unknown')}:{','.join(absent)}")
        source_path = REPO_ROOT / str(source.get("path", ""))
        if not source_path.exists():
            missing.append(f"{source.get('source_id', 'unknown')}:path_missing")
    if missing:
        return Decision(
            "DENY",
            ["INV-P1-EVIDENCE"],
            "RAG source manifest is incomplete.",
            ["Register only existing local sources with required citation fields."],
            missing,
        )
    return Decision("ALLOW", [], "RAG source manifest validates.", [], [])


def validate_skills_index(path: Path | None = None) -> Decision:
    """Validate skill index paths and metadata."""

    index_path = path or (REPO_ROOT / "controls" / "skills_index.json")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        policy = load_policy()
    except Exception as exc:
        return _decision_for_policy_error(exc, "codex")
    required = set(policy.get("skill_required_fields", []))
    missing: list[str] = []
    for skill in index.get("skills", []):
        absent = sorted(required.difference(skill))
        if absent:
            missing.append(f"{skill.get('name', 'unknown')}:{','.join(absent)}")
        skill_path = REPO_ROOT / str(skill.get("path", ""))
        if not skill_path.exists():
            missing.append(f"{skill.get('name', 'unknown')}:path_missing")
        elif f"name: {skill.get('name')}" not in skill_path.read_text(encoding="utf-8"):
            missing.append(f"{skill.get('name', 'unknown')}:metadata_missing")
    if missing:
        return Decision(
            "DENY",
            ["INV-REPORT-GATE"],
            "Skill index does not match .agents/skills placement.",
            ["Update controls/skills_index.json and skill metadata."],
            missing,
        )
    return Decision("ALLOW", [], "Skill index validates.", [], [])


def validate_stg_procedure(path: Path | None = None) -> Decision:
    """Validate the STG fixed procedure JSON."""

    proc_path = path or (REPO_ROOT / "controls" / "procedures" / "stg_deploy.json")
    try:
        procedure = json.loads(proc_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _decision_for_policy_error(exc, "codex")
    required = [
        "id",
        "type",
        "states",
        "allowed_hard_stop_predicates",
        "forbidden_stop_predicates",
        "decision_for_forbidden_stop",
    ]
    missing = [key for key in required if key not in procedure]
    if procedure.get("decision_for_forbidden_stop") != "DENY_STOP_CONTINUE_PROCEDURE":
        missing.append("decision_for_forbidden_stop")
    if missing:
        return Decision(
            "DENY",
            ["INV-FIXED-PROCEDURE"],
            "STG fixed procedure is incomplete.",
            ["Repair controls/procedures/stg_deploy.json."],
            missing,
        )
    return Decision("ALLOW", [], "STG fixed procedure validates.", [], [])


def run_self_test() -> dict[str, Any]:
    """Run invariant-category negative and positive self-tests."""

    cases: list[dict[str, Any]] = []

    def add(name: str, actual: Decision, expected: str) -> None:
        cases.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual.outcome,
                "ok": actual.outcome == expected,
                "invariants": actual.invariant_ids,
                "reason": actual.reason,
            }
        )

    impl_contract = Contract("IMPLEMENTATION_ALLOWED", turn_hash="test")
    question_contract = Contract("QUESTION_ONLY", turn_hash="test")
    review_contract = Contract("REVIEW_ONLY", turn_hash="test")
    deploy_contract = Contract("DEPLOY_ALLOWED", ["FIXED_PROCEDURE_BOUND"], "test", fixed_procedure=True, environment_mutation_allowed=True)
    prod_deploy_contract = classify_prompt("本番デプロイを行って")
    perf_contract = Contract("PERFORMANCE_EXPERIMENT", ["PERFORMANCE_EXPERIMENT"], "test", performance_experiment=True)

    add("reject hidden ignored rg files", evaluate_command("rg --files --hidden --no-ignore", impl_contract), "DENY")
    add("reject hidden ignored rg search", evaluate_command("rg pattern --hidden --no-ignore", impl_contract), "DENY")
    add("reject powershell recurse force", evaluate_command("Get-ChildItem -Recurse -Force", impl_contract), "DENY")
    add("reject find whole tree", evaluate_command("find . -type f", impl_contract), "DENY")
    add("reject ls recursive hidden", evaluate_command("ls -laR", impl_contract), "DENY")
    add("reject protected git config", evaluate_command("cat .git/config", impl_contract), "DENY")
    add("reject codex audit state", evaluate_command("cat .codex/audit/control_decisions.jsonl", impl_contract), "DENY")
    add("reject secret file", evaluate_command("cat .env", impl_contract), "DENY")
    add("reject parent traversal", evaluate_command("cat ../outside.txt", impl_contract), "DENY")
    add("allow explicit repo search", evaluate_command("rg specific_symbol src tests", impl_contract), "ALLOW")
    add("reject apply patch for question", evaluate_command("apply_patch update file", question_contract), "DENY")
    add("reject file edit for review", evaluate_tool_use(review_contract, "apply_patch", {"path": "README.md"}), "DENY")
    add("allow file edit for implementation", evaluate_tool_use(impl_contract, "apply_patch", {"path": "controls/policy.json"}), "ALLOW")
    add("reject direct live alias mutation", evaluate_command("aws lambda update-alias --function-name example --name live --function-version 9", perf_contract), "DENY")
    add("allow fixed deploy mutation", evaluate_command("aws cloudformation deploy --stack-name stg", deploy_contract), "ALLOW")
    add(
        "classify prod deploy fixed procedure",
        Decision(
            "ALLOW"
            if (
                prod_deploy_contract.work_type == "DEPLOY_ALLOWED"
                and prod_deploy_contract.fixed_procedure
                and prod_deploy_contract.environment_mutation_allowed
            )
            else "DENY",
            ["INV-CONTRACT-SCOPE"],
            "PROD deploy prompt classification includes fixed procedure and environment mutation.",
        ),
        "ALLOW",
    )
    add(
        "reject fixed procedure forbidden stop",
        evaluate_report("origin/dev..branch に複数 commit があるため確認が必要です。どちらで進めますか。", deploy_contract),
        "DENY_STOP_CONTINUE_PROCEDURE",
    )
    add(
        "reject cloudwatch user view claim",
        evaluate_report("CloudWatch のみでユーザー視点の表示改善を確認済みです。", perf_contract),
        "NEEDS_EVIDENCE",
    )
    add(
        "reject curl browser lcp claim",
        evaluate_report("curl time_total のみでブラウザ LCP 改善を確認済みです。", perf_contract),
        "NEEDS_EVIDENCE",
    )
    add(
        "allow browser navigation evidence",
        evaluate_report("ブラウザ表示は Navigation Timing と browser_navigation 証跡で確認した。", perf_contract),
        "ALLOW",
    )
    add(
        "allow unmeasured browser disclosure",
        evaluate_report("ユーザー視点の表示改善は未測定です。未測定のため断定しません。", perf_contract),
        "ALLOW",
    )
    add(
        "reject warm sample as cold",
        evaluate_report("cold-like first request として HTTP 500 後の初回 HTTP 200 と warm n=8 を採用した。", perf_contract),
        "NEEDS_EVIDENCE",
    )
    add(
        "reject snapstart without readiness",
        evaluate_report("SnapStart の測定は検証済みです。", perf_contract),
        "NEEDS_EVIDENCE",
    )
    add(
        "reject completion without matrix",
        evaluate_report("実装完了しました。", impl_contract),
        "NEEDS_EVIDENCE",
    )
    add(
        "allow incomplete with unknowns",
        evaluate_report("未確認事項: browser_paint は未確認。判定: 完了不可。", impl_contract),
        "ALLOW",
    )
    add(
        "allow completion with matrix",
        evaluate_report(
            "## 要件照合\n| 要件ID | 要件 | 実施内容 | 証跡 | 判定 | 未確認 |\n"
            "|---|---|---|---|---|---|\n| AC-001 | x | y | z | 満足 | なし |\n"
            "## 変更ファイル\n| ファイル | 変更内容 | 理由 |\n|---|---|---|\n| a | b | c |\n"
            "## 検証結果\n| コマンド | 結果 | 証跡 |\n|---|---|---|\n| t | 成功 | out |\n"
            "## 未確認事項\n- なし\n## 判定\n- 完了可否: 完了",
            impl_contract,
        ),
        "ALLOW",
    )
    deploy_completion_matrix = (
        "## 要件照合\n| 要件ID | 要件 | 実施内容 | 証跡 | 判定 | 未確認 |\n"
        "|---|---|---|---|---|---|\n| DEPLOY-001 | x | y | z | 満足 | なし |\n"
        "## 変更ファイル\n| ファイル | 変更内容 | 理由 |\n|---|---|---|\n| a | b | c |\n"
        "## 検証結果\n| コマンド | 結果 | 証跡 |\n|---|---|---|\n| t | 成功 | out |\n"
        "## 未確認事項\n- なし\n## 判定\n- デプロイ完了"
    )
    add(
        "reject deploy completion without aws confirmation",
        evaluate_report(deploy_completion_matrix, deploy_contract),
        "NEEDS_EVIDENCE",
    )
    add(
        "allow deploy completion with aws confirmation",
        evaluate_report(
            deploy_completion_matrix
            + "\n- AWS確認: CodePipeline Succeeded; CloudFormation UPDATE_COMPLETE; Lambda Active; HTTP 200.",
            deploy_contract,
        ),
        "ALLOW",
    )
    add(
        "reject incident record only prevention",
        evaluate_report("incident record を作成したため再発防止済みです。", Contract("INCIDENT_RESPONSE", turn_hash="test")),
        "NEEDS_EVIDENCE",
    )
    add("human manual push warn-only", evaluate_git_hook("pre-push", actor="human", dry_run=True), "WARN")
    add("codex main push denied", evaluate_git_hook("pre-push", actor="codex", branch_name="main", dry_run=True), "DENY")
    add("validate policy", validate_policy(), "ALLOW")
    add("validate stg procedure", validate_stg_procedure(), "ALLOW")

    return {"ok": all(case["ok"] for case in cases), "tests": cases}


def evaluate_git_hook(
    hook_name: str,
    actor: str | None = None,
    commit_msg_path: Path | None = None,
    branch_name: str | None = None,
    dry_run: bool = False,
) -> Decision:
    """Evaluate Git hook state using v2 actor semantics."""

    normalized_actor = normalize_actor(actor or actor_from_environment())
    if normalized_actor == "human":
        return Decision(
            "WARN",
            ["INV-HUMAN-NONBLOCKING"],
            "Human actor GitHook is warn-only and is not blocked by AI controls.",
            [],
            [],
        )
    if normalized_actor == "unknown":
        return Decision(
            "DENY",
            ["INV-HUMAN-NONBLOCKING"],
            "GitHook actor is unknown; set GUARD_ACTOR=human, codex, or ci.",
            ["Set GUARD_ACTOR explicitly before retrying."],
            ["actor evidence"],
        )

    hook = hook_name.strip()
    if hook == "pre-commit":
        return _evaluate_pre_commit(dry_run=dry_run)
    if hook == "commit-msg":
        return _evaluate_commit_msg(commit_msg_path)
    if hook == "pre-push":
        return _evaluate_pre_push(branch_name=branch_name, dry_run=dry_run)
    return Decision(
        "DENY",
        ["INV-REPORT-GATE"],
        f"Unsupported Git hook: {hook_name}",
        ["Use pre-commit, commit-msg, or pre-push."],
        ["hook name"],
    )


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a local Git read-only command for hook evaluation."""

    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _evaluate_pre_commit(dry_run: bool = False) -> Decision:
    """Inspect staged changes for secret-like content and control schema validity."""

    if dry_run:
        return Decision("ALLOW", [], "Dry-run pre-commit check passes.", [], [])
    names = _run_git(["diff", "--cached", "--name-only"])
    diff = _run_git(["diff", "--cached", "--unified=0"])
    if names.returncode != 0 or diff.returncode != 0:
        return Decision(
            "DENY",
            ["INV-P1-EVIDENCE"],
            "Unable to inspect staged diff.",
            ["Repair Git state or run the hook from repository root."],
            ["git diff --cached output"],
        )
    staged = [line.strip() for line in names.stdout.splitlines() if line.strip()]
    forbidden = [path for path in staged if path.startswith(".codex/audit/") or path.startswith(".codex/state/") or path == ".git/config"]
    if forbidden:
        return Decision(
            "DENY",
            ["INV-ASSET-REACHABILITY"],
            "Staged changes include protected control assets.",
            ["Unstage protected assets before AI/CI commit."],
            forbidden,
        )
    if re.search(r"(?i)(sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,}|BEGIN (RSA|OPENSSH) PRIVATE KEY)", diff.stdout):
        return Decision(
            "DENY",
            ["INV-ASSET-REACHABILITY"],
            "Staged diff contains credential-like content.",
            ["Remove secret-like content before committing."],
            ["redacted staged diff evidence"],
        )
    if "controls/policy.json" in staged:
        policy_decision = validate_policy()
        if policy_decision.outcome != "ALLOW":
            return policy_decision
    for path in staged:
        if path.startswith("docs/incidents/") and path.endswith(".md"):
            content_path = REPO_ROOT / path
            if content_path.exists():
                text = content_path.read_text(encoding="utf-8", errors="replace")
                missing = [
                    term
                    for term in (
                        "root cause",
                        "violated invariant",
                        "control change",
                        "regression self-test",
                        "verification evidence",
                        "remaining risk",
                    )
                    if term not in text
                ]
                if missing:
                    return Decision(
                        "DENY",
                        ["INV-INCIDENT-LIFECYCLE"],
                        "Incident record is missing required lifecycle sections.",
                        ["Complete incident lifecycle fields before commit."],
                        missing,
                    )
    self_test = run_self_test()
    if not self_test["ok"]:
        failed = [case["name"] for case in self_test["tests"] if not case["ok"]]
        return Decision(
            "DENY",
            ["INV-REPORT-GATE"],
            "Control self-test failed during pre-commit.",
            ["Repair failed control tests before commit."],
            failed,
        )
    return Decision("ALLOW", [], "Pre-commit control checks pass.", [], [])


def _evaluate_commit_msg(path: Path | None) -> Decision:
    """Inspect commit message claims for evidence references."""

    if path is None or not path.exists():
        return Decision(
            "DENY",
            ["INV-P1-EVIDENCE"],
            "commit-msg hook did not receive a readable message path.",
            ["Retry commit with a readable commit message file."],
            ["commit message path"],
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    policy = load_policy()
    if _has_any(text, policy["report_gate"]["completion_terms"]):
        if not _has_any(text, ["証跡:", "Evidence:", "Refs:", "要件ID", "検証結果"]):
            return Decision(
                "DENY",
                ["INV-REPORT-GATE"],
                "Completion-like commit message lacks evidence reference.",
                ["Add evidence reference in the commit body."],
                ["commit body evidence reference"],
            )
    if _has_any(text, ["incident", "インシデント"]) and not _has_any(text, ["severity", "重大度"]):
        return Decision(
            "DENY",
            ["INV-INCIDENT-LIFECYCLE"],
            "Incident commit message lacks severity evidence.",
            ["Record severity or state that severity is unknown in the body."],
            ["severity evidence"],
        )
    return Decision("ALLOW", [], "Commit message control checks pass.", [], [])


def _evaluate_pre_push(branch_name: str | None = None, dry_run: bool = False) -> Decision:
    """Inspect branch-level push restrictions for strict actors."""

    branch = branch_name
    if branch is None and not dry_run:
        result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if result.returncode != 0:
            return Decision(
                "DENY",
                ["INV-P1-EVIDENCE"],
                "Unable to identify current branch before push.",
                ["Run from a valid Git repository and retry."],
                ["git branch evidence"],
            )
        branch = result.stdout.strip()
    if branch in {"main", "dev"}:
        return Decision(
            "DENY",
            ["INV-HUMAN-NONBLOCKING"],
            "AI/CI direct push to main or dev is denied.",
            ["Use the project branch-finalization procedure."],
            ["branch name"],
        )
    return Decision(
        "ALLOW",
        [],
        "Pre-push strict checks pass; commit range size is not a fixed-procedure stop predicate.",
        [],
        [],
    )
