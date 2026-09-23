"""Standard job and agent-result records.

These are the only handoff objects the orchestrator passes between logical
agents. Shapes are validated against JSON schemas so the protocol stays
inspectable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..validation import validate


JOB_STATUSES = {
    "pending",
    "assigned",
    "in_progress",
    "completed",
    "failed",
    "blocked",
    "retrying",
}


DEFAULT_RETRYABLE_ERRORS = ("transient_agent_error", "temporary_unavailable")
DEFAULT_TERMINAL_ERRORS = (
    "terminal_agent_error",
    "prohibited_action",
    "schema_violation",
    "phase_blocked",
    "unknown_agent_runtime",
)


@dataclass
class RetryPolicy:
    max_attempts: int = 2
    retryable_error_codes: tuple = DEFAULT_RETRYABLE_ERRORS
    terminal_error_codes: tuple = DEFAULT_TERMINAL_ERRORS

    def to_dict(self) -> dict:
        return {
            "max_attempts": self.max_attempts,
            "retryable_error_codes": list(self.retryable_error_codes),
            "terminal_error_codes": list(self.terminal_error_codes),
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "RetryPolicy":
        data = data or {}
        return cls(
            max_attempts=int(data.get("max_attempts", 2)),
            retryable_error_codes=tuple(data.get("retryable_error_codes", DEFAULT_RETRYABLE_ERRORS)),
            terminal_error_codes=tuple(data.get("terminal_error_codes", DEFAULT_TERMINAL_ERRORS)),
        )


@dataclass
class Job:
    job_id: str
    project_id: str
    workflow_id: str
    agent_id: str
    objective: str
    required_inputs: List[dict]
    supplied_inputs: Dict[str, Any]
    dependencies: List[str]
    status: str
    permission_class: str
    created_at: str
    evidence_requirements: List[str]
    expected_output_schema: Dict[str, Any]
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    stage_id: str = ""
    attempts: int = 0

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "workflow_id": self.workflow_id,
            "agent_id": self.agent_id,
            "objective": self.objective,
            "required_inputs": list(self.required_inputs),
            "supplied_inputs": self.supplied_inputs,
            "dependencies": list(self.dependencies),
            "status": self.status,
            "permission_class": self.permission_class,
            "created_at": self.created_at,
            "evidence_requirements": list(self.evidence_requirements),
            "expected_output_schema": self.expected_output_schema,
            "retry_policy": self.retry_policy.to_dict(),
            "stage_id": self.stage_id,
            "attempts": self.attempts,
        }

    def validate(self) -> None:
        validate(self.to_dict(), "job", source=f"job:{self.job_id}")


@dataclass
class AgentResult:
    job_id: str
    agent_id: str
    status: str
    findings: List[dict]
    structured_output: Dict[str, Any]
    evidence: List[str]
    assumptions: List[dict]
    unknowns: List[str]
    confidence: Dict[str, Any]
    validation_flags: List[str]
    recommended_next_action: str
    errors: List[dict]

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "findings": list(self.findings),
            "structured_output": self.structured_output,
            "evidence": list(self.evidence),
            "assumptions": list(self.assumptions),
            "unknowns": list(self.unknowns),
            "confidence": self.confidence,
            "validation_flags": list(self.validation_flags),
            "recommended_next_action": self.recommended_next_action,
            "errors": list(self.errors),
        }

    def validate(self) -> None:
        validate(self.to_dict(), "agent_result", source=f"result:{self.job_id}")


def simulation_confidence(level: str, basis: str) -> Dict[str, Any]:
    return {
        "level": level,
        "basis": basis,
        "scope": "offline_simulation",
        "notes": (
            "Confidence scores only whether TEST/MOCK inputs satisfied explicit rules. "
            "It is not a real-world probability."
        ),
    }


def make_result(
    job: Job,
    *,
    status: str = "completed",
    findings: Optional[List[dict]] = None,
    structured_output: Optional[dict] = None,
    evidence: Optional[List[str]] = None,
    assumptions: Optional[List[dict]] = None,
    unknowns: Optional[List[str]] = None,
    confidence: Optional[dict] = None,
    validation_flags: Optional[List[str]] = None,
    recommended_next_action: str = "proceed",
    errors: Optional[List[dict]] = None,
) -> AgentResult:
    result = AgentResult(
        job_id=job.job_id,
        agent_id=job.agent_id,
        status=status,
        findings=list(findings or []),
        structured_output=dict(structured_output or {}),
        evidence=list(evidence or []),
        assumptions=list(assumptions or []),
        unknowns=list(unknowns or []),
        confidence=confidence
        or simulation_confidence("not_applicable", "No confidence basis supplied."),
        validation_flags=list(validation_flags or []),
        recommended_next_action=recommended_next_action,
        errors=list(errors or []),
    )
    result.validate()
    return result
