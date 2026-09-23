"""Shared helpers for offline logical agents."""
from __future__ import annotations

from typing import Any, Dict, List

from ...protocol.knowledge import claim
from ...protocol.models import Job, simulation_confidence


FIXTURE_AGENTS = frozenset({"trend_discovery_agent", "market_research_agent"})


def stage_output(job: Job, stage_id: str) -> Dict[str, Any]:
    upstream = (job.supplied_inputs or {}).get("upstream") or {}
    output = upstream.get(stage_id) or {}
    return output if isinstance(output, dict) else {}


def fixture_of(job: Job) -> Dict[str, Any]:
    fixture = (job.supplied_inputs or {}).get("fixture") or {}
    return fixture if isinstance(fixture, dict) else {}


def passthrough_claim(node: Any, field: str) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return claim(
            claim_id=f"missing-{field}",
            field=field,
            statement=f"{field} was not supplied.",
            epistemic_status="UNKNOWN",
        )
    return claim(
        claim_id=node.get("claim_id") or f"claim-{field}",
        field=node.get("field") or field,
        statement=node.get("statement") or "UNKNOWN",
        epistemic_status=node.get("epistemic_status") or "UNKNOWN",
        evidence_ids=list(node.get("evidence_ids") or []),
        notes=node.get("notes") or "",
    )


def confidence_for(level: str, basis: str) -> dict:
    return simulation_confidence(level, basis)


def cited_evidence_ids(payload: Any) -> List[str]:
    found: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for evidence_id in node.get("evidence_ids") or []:
                if evidence_id not in found:
                    found.append(evidence_id)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found
