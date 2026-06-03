"""Shared policy engine for CodexHook, Shell wrapper, GitHook, CI, reports, and self-test."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Mapping

from scripts.control import command_policy, git_policy, incident_policy, prompt_contract, report_policy

Outcome = Literal["ALLOW", "DENY", "WARN", "NEEDS_HUMAN", "NEEDS_EVIDENCE", "NEEDS_CONTINUATION", "ERROR"]
Actor = Literal["codex", "chatgpt", "ci", "human", "unknown"]


@dataclass(frozen=True)
class RuntimeContext:
    """Runtime facts supplied by a hook, wrapper, CI job, or CLI invocation."""

    actor: Actor = "unknown"
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Contract:
    """Current-turn contract derived from the user prompt."""

    turn_id: str
    actor: Actor
    work_type: set[str]
    explicit_instructions: list[str]
    obligations: list[str]
    acceptance_criteria: list[str]
    ambiguity_items: list[str]
    allowed_assets: list[str]
    prohibited_assets: list[str]
    allowed_tools: list[str]
    prohibited_tools: list[str]
    deploy_allowed: bool
    evidence_requirements: list[str]

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        data = asdict(self)
        data["work_type"] = sorted(self.work_type)
        return data


@dataclass(frozen=True)
class Decision:
    """Policy decision returned by every control gate."""

    outcome: Outcome
    invariant_ids: list[str]
    reason: str
    evidence_required: list[str] = field(default_factory=list)
    allowed_next_actions: list[str] = field(default_factory=list)
    audit_redactions: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def classify_prompt(prompt: str, context: RuntimeContext) -> Contract:
    """Create a current-turn contract from the user prompt."""
    data = prompt_contract.classify_prompt_data(prompt, actor=context.actor, env=context.env)
    return Contract(
        turn_id=str(data["turn_id"]),
        actor=_actor(str(data["actor"])),
        work_type=set(str(item) for item in data["work_type"]),
        explicit_instructions=[str(item) for item in data["explicit_instructions"]],
        obligations=[str(item) for item in data["obligations"]],
        acceptance_criteria=[str(item) for item in data["acceptance_criteria"]],
        ambiguity_items=[str(item) for item in data["ambiguity_items"]],
        allowed_assets=[str(item) for item in data["allowed_assets"]],
        prohibited_assets=[str(item) for item in data["prohibited_assets"]],
        allowed_tools=[str(item) for item in data["allowed_tools"]],
        prohibited_tools=[str(item) for item in data["prohibited_tools"]],
        deploy_allowed=bool(data["deploy_allowed"]),
        evidence_requirements=[str(item) for item in data["evidence_requirements"]],
    )


def evaluate_tool_use(contract: Contract, tool_name: str, tool_input: dict[str, object]) -> Decision:
    """Evaluate a tool request before it runs."""
    command = _extract_command(tool_name, tool_input)
    if tool_name in {"apply_patch", "functions.apply_patch"} and "IMPLEMENTATION_ALLOWED" not in contract.work_type:
        return Decision(
            outcome="DENY",
            invariant_ids=["INV-P1-003"],
            reason="apply_patch lacks implementation permission in the current contract",
            allowed_next_actions=["file edit の明示許可を取得してください。"],
        )
    if command:
        return _decision_from_mapping(command_policy.evaluate_command(command, contract=contract))
    return Decision(outcome="ALLOW", invariant_ids=[], reason="tool policy allowed")


def evaluate_permission_request(contract: Contract, request: dict[str, object]) -> Decision:
    """Evaluate sandbox, network, or permission escalation requests."""
    text = " ".join(str(value) for value in request.values())
    if any(term in text.lower() for term in ("network", "bypass", "deploy", "aws", "write")):
        if "IMPLEMENTATION_ALLOWED" not in contract.work_type and not contract.deploy_allowed:
            return Decision(
                outcome="DENY",
                invariant_ids=["INV-P1-003"],
                reason="permission request lacks explicit current-turn work permission",
                allowed_next_actions=["要求する権限と根拠を現在ターンで明示してください。"],
            )
    return Decision(outcome="ALLOW", invariant_ids=[], reason="permission request allowed")


def evaluate_tool_result(
    contract: Contract,
    tool_name: str,
    tool_input: dict[str, object],
    tool_result: dict[str, object],
) -> Decision:
    """Evaluate tool output after execution for leakage or policy bypass evidence."""
    output_text = " ".join(str(value) for value in tool_result.values())
    lowered = output_text.lower()
    if any(marker in lowered for marker in ("aws_access_key_id", "private key", "secret_access_key")):
        return Decision(
            outcome="DENY",
            invariant_ids=["INV-P2-002"],
            reason="tool output appears to contain secret material",
            audit_redactions=["secret-like output"],
        )
    return Decision(outcome="ALLOW", invariant_ids=[], reason="tool result allowed")


def evaluate_report(contract: Contract, response_text: str, *, stop_event: bool = False) -> Decision:
    """Evaluate a report against evidence requirements."""
    return _decision_from_mapping(report_policy.evaluate_report_text(response_text, stop_event=stop_event))


def evaluate_git_change(contract: Contract, staged_diff: str, hook_type: str) -> Decision:
    """Evaluate Git hook data."""
    return _decision_from_mapping(
        git_policy.evaluate_git_change(hook_type=hook_type, actor=contract.actor, staged_diff=staged_diff)
    )


def evaluate_deploy(contract: Contract, command: str, env: Mapping[str, str]) -> Decision:
    """Evaluate deploy command requirements."""
    return _decision_from_mapping(
        command_policy.evaluate_command(command, contract=contract, env=env)
    )


def evaluate_incident_record(contract: Contract, record_text: str) -> Decision:
    """Evaluate required incident lifecycle fields."""
    return _decision_from_mapping(incident_policy.evaluate_incident_record_text(record_text))


def default_contract(actor: Actor = "codex", *, deploy_allowed: bool = False) -> Contract:
    """Return a minimal implementation contract for CLI and self-test use."""
    work_type = {"IMPLEMENTATION_ALLOWED"}
    if deploy_allowed:
        work_type.add("DEPLOY_ALLOWED")
    return Contract(
        turn_id="default",
        actor=actor,
        work_type=work_type,
        explicit_instructions=["default implementation contract"],
        obligations=["evidence required"],
        acceptance_criteria=[],
        ambiguity_items=[],
        allowed_assets=[],
        prohibited_assets=[],
        allowed_tools=[],
        prohibited_tools=[],
        deploy_allowed=deploy_allowed,
        evidence_requirements=["証跡"],
    )


def _extract_command(tool_name: str, tool_input: dict[str, object]) -> str:
    """Return a shell command text from supported tool input shapes."""
    if "command" in tool_input:
        return str(tool_input["command"])
    if tool_name.lower() in {"shell", "shell_command", "functions.shell_command"}:
        return " ".join(str(value) for value in tool_input.values())
    return ""


def _decision_from_mapping(data: Mapping[str, object]) -> Decision:
    """Convert a module finding into the public Decision dataclass."""
    return Decision(
        outcome=_outcome(str(data.get("outcome", "ERROR"))),
        invariant_ids=[str(item) for item in data.get("invariant_ids", [])],
        reason=str(data.get("reason", "")),
        evidence_required=[str(item) for item in data.get("evidence_required", [])],
        allowed_next_actions=[str(item) for item in data.get("allowed_next_actions", [])],
        audit_redactions=[str(item) for item in data.get("audit_redactions", [])],
    )


def _actor(value: str) -> Actor:
    """Normalize an actor value."""
    if value in {"codex", "chatgpt", "ci", "human", "unknown"}:
        return value  # type: ignore[return-value]
    return "unknown"


def _outcome(value: str) -> Outcome:
    """Normalize a decision outcome."""
    if value in {"ALLOW", "DENY", "WARN", "NEEDS_HUMAN", "NEEDS_EVIDENCE", "NEEDS_CONTINUATION", "ERROR"}:
        return value  # type: ignore[return-value]
    return "ERROR"
