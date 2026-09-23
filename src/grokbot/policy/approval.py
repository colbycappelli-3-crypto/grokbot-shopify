"""Approval / permission system.

Every consequential action belongs to exactly one class:

* ``AUTONOMOUS`` — low-risk, reversible, no external side effects.
* ``APPROVAL_REQUIRED`` — material external actions needing human owner approval.
* ``PROHIBITED`` — must never be performed by any agent.

The mapping from action *category* to class is owner-editable via the policy
config. ``PROHIBITED`` categories are safety-critical and cannot be relaxed by
an in-memory override.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List

from ..resources import config_dir
from ..validation import load_and_validate

DEFAULT_POLICY_FILENAME = "approval_policy.yaml"


class ActionClass(str, Enum):
    AUTONOMOUS = "AUTONOMOUS"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    PROHIBITED = "PROHIBITED"


@dataclass(frozen=True)
class ApprovalDecision:
    category: str
    action_class: ActionClass
    matched: bool

    @property
    def allowed_autonomously(self) -> bool:
        return self.action_class is ActionClass.AUTONOMOUS

    @property
    def requires_approval(self) -> bool:
        return self.action_class is ActionClass.APPROVAL_REQUIRED

    @property
    def prohibited(self) -> bool:
        return self.action_class is ActionClass.PROHIBITED


class ApprovalPolicy:
    def __init__(self, data: dict):
        self._data = data
        self.version: str = data["version"]
        self.default_class = ActionClass(data["default_class"])
        self.owner_can_override: bool = data.get("owner_can_override", True)
        self._rules: Dict[str, ActionClass] = {
            rule["category"]: ActionClass(rule["class"]) for rule in data["rules"]
        }
        self._overrides: Dict[str, ActionClass] = {}

    @classmethod
    def from_file(cls, path: Path) -> "ApprovalPolicy":
        return cls(load_and_validate(Path(path), "approval_policy"))

    def categories(self) -> List[str]:
        return sorted(self._rules)

    def classify(self, category: str) -> ApprovalDecision:
        matched = category in self._overrides or category in self._rules
        action_class = self._overrides.get(
            category, self._rules.get(category, self.default_class)
        )
        return ApprovalDecision(category=category, action_class=action_class, matched=matched)

    def set_override(self, category: str, action_class: ActionClass) -> None:
        """Owner override. PROHIBITED categories can never be relaxed."""
        if not self.owner_can_override:
            raise PermissionError("Policy is locked; owner_can_override is false.")
        action_class = ActionClass(action_class)
        base = self._rules.get(category)
        if base is ActionClass.PROHIBITED and action_class is not ActionClass.PROHIBITED:
            raise PermissionError(
                f"Category '{category}' is PROHIBITED and cannot be relaxed via override."
            )
        self._overrides[category] = action_class


def load_default_policy() -> ApprovalPolicy:
    return ApprovalPolicy.from_file(config_dir() / DEFAULT_POLICY_FILENAME)
