"""Structured audit log.

Important orchestration events are appended here. Secret-like keys and
recognizable credential values are redacted before the entry is stored.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List

from ..clock import utc_now
from ..validation import validate

AUDIT_EVENT_TYPES = (
    "project_created",
    "job_created",
    "job_assigned",
    "job_completed",
    "job_failed",
    "evidence_added",
    "validation_gate_evaluated",
    "workflow_stopped",
    "approval_requested",
    "approval_decision",
    "action_blocked",
    "retry_scheduled",
    "decision_recorded",
    "review_enqueued",
    "review_decision",
    "action_proposed",
    "action_decision",
    "gate_advanced",
    "execution_withheld",
)

_SECRET_KEY = re.compile(
    r"(api[_-]?key|secret|token|password|credential|private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(sk_live_|sk_test_|ghp_|xox[baprs]-|AKIA[0-9A-Z]{16}|-----BEGIN )"
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEY.search(str(key)):
                cleaned[str(key)] = "[REDACTED]"
            else:
                cleaned[str(key)] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and _SECRET_VALUE.search(value):
        return "[REDACTED]"
    return value


class AuditLog:
    def __init__(self) -> None:
        self.events: List[dict] = []

    def record(self, event_type: str, **details: Any) -> dict:
        entry = {
            "event_id": f"aud-{uuid.uuid4().hex[:12]}",
            "timestamp": utc_now(),
            "event_type": event_type,
            "details": redact(details),
        }
        validate(entry, "audit_event", source=f"audit:{event_type}")
        self.events.append(entry)
        return entry

    def of_type(self, event_type: str) -> List[dict]:
        return [event for event in self.events if event["event_type"] == event_type]

    def to_list(self) -> List[dict]:
        return list(self.events)
