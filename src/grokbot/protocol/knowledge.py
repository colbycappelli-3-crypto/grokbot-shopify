"""Epistemic status for claims passed between agents.

FACT, INFERENCE, ASSUMPTION, and UNKNOWN are distinct. A FACT is accepted only
when every cited evidence record exists and is verified. Mock support stays
labeled TEST/MOCK. Unsupported FACT claims are downgraded to UNKNOWN before a
downstream agent can read them.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EpistemicStatus(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    ASSUMPTION = "ASSUMPTION"
    UNKNOWN = "UNKNOWN"


EPISTEMIC_VALUES = {status.value for status in EpistemicStatus}
SECTION_EPISTEMIC_VALUES = EPISTEMIC_VALUES | {"MIXED", "NOT_APPLICABLE"}


def is_claim(node: Any) -> bool:
    return isinstance(node, dict) and "statement" in node and "epistemic_status" in node


def enforce_structured_output(
    payload: Any,
    evidence_index: Dict[str, Any],
) -> Tuple[Any, List[str]]:
    """Return a copy of ``payload`` with unsupported FACT claims downgraded."""
    flags: List[str] = []
    return _walk(payload, evidence_index, flags), flags


def _walk(node: Any, evidence_index: Dict[str, Any], flags: List[str]) -> Any:
    if is_claim(node):
        return _enforce_claim(dict(node), evidence_index, flags)
    if isinstance(node, dict):
        return {key: _walk(value, evidence_index, flags) for key, value in node.items()}
    if isinstance(node, list):
        return [_walk(item, evidence_index, flags) for item in node]
    return node


def _enforce_claim(claim: Dict[str, Any], evidence_index: Dict[str, Any], flags: List[str]) -> Dict[str, Any]:
    status = claim.get("epistemic_status")
    if status not in EPISTEMIC_VALUES:
        flags.append("invalid_epistemic_status_downgraded")
        claim["epistemic_status"] = EpistemicStatus.UNKNOWN.value
        claim["support_scope"] = "none"
        claim["notes"] = _note(claim, "Invalid epistemic status replaced with UNKNOWN.")
        return claim

    evidence_ids = list(claim.get("evidence_ids") or [])
    claim["evidence_ids"] = evidence_ids
    if status != EpistemicStatus.FACT.value:
        claim.setdefault("support_scope", "none")
        return claim

    records = [evidence_index.get(evidence_id) for evidence_id in evidence_ids]
    supported = bool(evidence_ids) and all(
        record is not None and record.verification_status == "verified" for record in records
    )
    if not supported:
        flags.append("unsupported_fact_downgraded")
        claim["epistemic_status"] = EpistemicStatus.UNKNOWN.value
        claim["support_scope"] = "none"
        claim["notes"] = _note(
            claim,
            "Unsupported FACT downgraded to UNKNOWN. A FACT requires verified evidence.",
        )
        return claim

    mock_support = any(record.source_type in {"mock", "test"} for record in records if record)
    if mock_support:
        claim["support_scope"] = "mock"
        claim["notes"] = _note(
            claim,
            "FACT only inside this offline simulation; supporting evidence is TEST/MOCK.",
        )
    else:
        claim.setdefault("support_scope", "operator_supplied")
    return claim


def _note(claim: Dict[str, Any], text: str) -> str:
    existing = (claim.get("notes") or "").strip()
    if text in existing:
        return existing
    return f"{existing} {text}".strip()


def claim(
    claim_id: str,
    field: str,
    statement: str,
    epistemic_status: str,
    evidence_ids: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    status = epistemic_status if epistemic_status in EPISTEMIC_VALUES else EpistemicStatus.UNKNOWN.value
    return {
        "claim_id": claim_id,
        "field": field,
        "statement": statement,
        "epistemic_status": status,
        "evidence_ids": list(evidence_ids or []),
        "notes": notes,
    }


def status_of(node: Any, default: str = "UNKNOWN") -> str:
    if not isinstance(node, dict):
        return default
    status = node.get("epistemic_status", default)
    return status if status in EPISTEMIC_VALUES else default


def iter_claims(node: Any):
    """Yield claim dicts (statement + epistemic_status) in a payload."""
    if is_claim(node):
        yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from iter_claims(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_claims(item)
