"""Persistent human review queue.

Decisions are recorded locally. Approving, denying, or requesting more research
does not purchase, publish, contact a supplier, message a customer, place a
Fiverr order, or issue a refund.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, List, Optional

from ..clock import utc_now
from ..resources import repo_root
from ..validation import SpecValidationError, validate


def default_review_dir() -> Path:
    return repo_root() / ".grokbot_state" / "reviews"


class ReviewStateError(ValueError):
    pass


def _unique(texts: List[str]) -> List[str]:
    seen = []
    for text in texts:
        if text not in seen:
            seen.append(text)
    return seen


def _text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("statement", "unknown", "message", "field"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        return "UNKNOWN"
    return str(item)


def _recommendation_summary(result: Any) -> str:
    output = result.structured_output if isinstance(result.structured_output, dict) else {}
    parts = [str(result.recommended_next_action)]
    for key in ("validation_outcome", "publish_status", "project_state", "offer_known"):
        if key in output and output[key] is not None:
            parts.append(f"{key}={output[key]}")
    if output.get("message_sent") is False:
        parts.append("message_sent=false")
    if output.get("refund_issued") is False:
        parts.append("refund_issued=false")
    if output.get("store_launched") is False:
        parts.append("store_launched=false")
    if output.get("commitment_made") is False:
        parts.append("commitment_made=false")
    return "; ".join(parts)


def build_review_item(run: Any, approval_block_reason: Optional[str] = None) -> dict:
    dossier = run.dossier or {}
    sections = dossier.get("sections") or {}
    unknowns = _unique(_text(item) for item in (sections.get("unknowns") or {}).get("content") or [])
    risks = _unique(_text(item) for item in (sections.get("risks") or {}).get("content") or [])
    recommendations = []
    for stage_id, result in run.results.items():
        recommendations.append(
            {
                "agent_id": result.agent_id,
                "stage_id": stage_id,
                "recommended_next_action": result.recommended_next_action,
                "summary": _recommendation_summary(result),
            }
        )
    banner = dossier.get("banner") or "UNSOURCED"
    summary = (
        f"{banner} Stop reason: {run.stop_reason}. "
        "No external action was performed. Approval does not execute one."
    )
    return {
        "review_id": f"rev-{uuid.uuid4().hex[:12]}",
        "project_id": run.project.project_id,
        "workflow_id": run.workflow.id,
        "division": run.workflow.division,
        "status": "pending",
        "objective": run.objective,
        "data_classification": dossier.get("data_classification") or "UNSOURCED",
        "banner": banner,
        "recommendations": recommendations,
        "unknowns": unknowns,
        "risks": risks,
        "dossier_id": dossier.get("dossier_id"),
        "summary": summary,
        "approval_block_reason": approval_block_reason,
        "decision": None,
        "consequential_actions_performed": [],
        "created_at": utc_now(),
    }


class ReviewQueue:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / "queue.json"

    def list_items(self) -> List[dict]:
        return list(self._read())

    def get(self, review_id: str) -> dict:
        for item in self._read():
            if item["review_id"] == review_id:
                return item
        raise ReviewStateError(f"Unknown review '{review_id}'.")

    def enqueue(self, item: dict) -> dict:
        validate(item, "review_item", source=f"review:{item.get('review_id', '<new>')}")
        items = self._read()
        if any(existing["review_id"] == item["review_id"] for existing in items):
            raise ReviewStateError(f"Review '{item['review_id']}' is already queued.")
        items.append(item)
        self._write(items)
        return item

    def decide(
        self,
        review_id: str,
        decision: str,
        note: str = "",
        decided_by: str = "human_owner",
    ) -> dict:
        if decision not in {"approved", "denied", "research_requested"}:
            raise ValueError("Review decision must be approved, denied, or research_requested.")
        items = self._read()
        target = None
        for item in items:
            if item["review_id"] == review_id:
                target = item
                break
        if target is None:
            raise ReviewStateError(f"Unknown review '{review_id}'.")
        if target["status"] != "pending":
            raise ReviewStateError(f"Review '{review_id}' is already {target['status']}.")
        blocked_reason = None
        recorded = decision
        status = {
            "approved": "approved",
            "denied": "denied",
            "research_requested": "research_requested",
        }[decision]
        if decision == "approved" and target.get("approval_block_reason"):
            recorded = "blocked"
            status = "pending"
            blocked_reason = target["approval_block_reason"]
        target["status"] = status
        target["decision"] = {
            "decision": recorded,
            "note": note,
            "decided_by": decided_by,
            "decided_at": utc_now(),
            "executed_external_action": False,
            "blocked_reason": blocked_reason,
        }
        target["consequential_actions_performed"] = []
        validate(target, "review_item", source=f"review:{review_id}")
        self._write(items)
        return target

    def _read(self) -> List[dict]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ReviewStateError(f"{self.path}: review queue must contain an items list.")
        loaded = []
        for item in items:
            try:
                validate(item, "review_item", source=str(self.path))
            except SpecValidationError as exc:
                raise ReviewStateError(str(exc)) from exc
            loaded.append(item)
        return loaded

    def _write(self, items: List[dict]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"items": items}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
