"""Project / store state.

Tracks a single project/store across workflow stages and gates, keeping an
auditable record of decisions, approvals, escalations, and evidence.

Quality principle enforced here: findings default to ``UNKNOWN`` and may only be
marked ``verified`` when at least one source is attached. Agents must never
manufacture facts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from ..policy.approval import ActionClass
from ..validation import validate


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProjectState:
    SCHEMA = "project_state"

    def __init__(self, data: dict):
        validate(data, self.SCHEMA, source=f"project:{data.get('project_id', '?')}")
        self._data = data

    @classmethod
    def new(
        cls,
        project_id: str,
        name: str,
        division: str,
        workflow_id: Optional[str] = None,
        stages: Optional[Iterable[str]] = None,
    ) -> "ProjectState":
        now = _utcnow()
        data: Dict[str, Any] = {
            "project_id": project_id,
            "name": name,
            "division": division,
            "status": "proposed",
            "created_at": now,
            "updated_at": now,
            "stages": [
                {"stage_id": sid, "status": "pending", "updated_at": now}
                for sid in (stages or [])
            ],
            "evidence": {},
            "decisions": [],
            "approvals": [],
            "escalations": [],
        }
        if workflow_id:
            data["workflow_id"] = workflow_id
        return cls(data)

    # ---- accessors -------------------------------------------------------
    @property
    def project_id(self) -> str:
        return self._data["project_id"]

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def data(self) -> dict:
        return self._data

    def stage(self, stage_id: str) -> dict:
        for stage in self._data["stages"]:
            if stage["stage_id"] == stage_id:
                return stage
        raise KeyError(stage_id)

    # ---- mutations (each re-validates against the schema) ----------------
    def _touch(self) -> None:
        self._data["updated_at"] = _utcnow()

    def _revalidate(self) -> None:
        validate(self._data, self.SCHEMA, source=f"project:{self.project_id}")

    def set_status(self, status: str) -> None:
        self._data["status"] = status
        self._touch()
        self._revalidate()

    def update_stage(self, stage_id: str, status: str, notes: Optional[str] = None) -> dict:
        stage = self.stage(stage_id)
        stage["status"] = status
        stage["updated_at"] = _utcnow()
        if notes is not None:
            stage["notes"] = notes
        self._touch()
        self._revalidate()
        return stage

    def record_evidence(
        self,
        key: str,
        value: Any = None,
        sources: Optional[Iterable[str]] = None,
        verified: bool = False,
    ) -> dict:
        sources = list(sources or [])
        if verified and not sources:
            raise ValueError("Cannot mark evidence 'verified' without at least one source.")
        if value is None:
            status = "UNKNOWN"
        elif verified:
            status = "verified"
        else:
            status = "unverified"
        item: Dict[str, Any] = {"status": status, "updated_at": _utcnow()}
        if value is not None:
            item["value"] = value
        if sources:
            item["sources"] = sources
        self._data.setdefault("evidence", {})[key] = item
        self._touch()
        self._revalidate()
        return item

    def add_decision(
        self,
        actor: str,
        summary: str,
        rationale: Optional[str] = None,
        references: Optional[Iterable[str]] = None,
    ) -> dict:
        entry: Dict[str, Any] = {"timestamp": _utcnow(), "actor": actor, "summary": summary}
        if rationale:
            entry["rationale"] = rationale
        if references:
            entry["references"] = list(references)
        self._data.setdefault("decisions", []).append(entry)
        self._touch()
        self._revalidate()
        return entry

    def request_approval(self, action: str, action_class: ActionClass) -> dict:
        entry = {
            "action": action,
            "action_class": ActionClass(action_class).value,
            "status": "pending",
            "timestamp": _utcnow(),
        }
        self._data.setdefault("approvals", []).append(entry)
        self._touch()
        self._revalidate()
        return entry

    def escalate(self, reason: str) -> dict:
        entry = {"timestamp": _utcnow(), "reason": reason, "status": "open"}
        self._data.setdefault("escalations", []).append(entry)
        self._touch()
        self._revalidate()
        return entry

    # ---- serialization ---------------------------------------------------
    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self._data, indent=2, **kwargs)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self._data, sort_keys=False)

    def save(self, path: Path) -> None:
        path = Path(path)
        text = self.to_yaml() if path.suffix in (".yaml", ".yml") else self.to_json()
        path.write_text(text, encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ProjectState":
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(fh)
            else:
                data = json.load(fh)
        return cls(data)
