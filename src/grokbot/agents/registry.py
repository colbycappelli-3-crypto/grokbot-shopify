"""Agent registry.

Agents are declarative specifications loaded from YAML and validated against the
agent schema. The registry indexes them by id and provides lookups. It does NOT
start any process — specs describe logical roles only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..policy.approval import ActionClass
from ..resources import AGENT_SPECS_DIR
from ..validation import iter_spec_files, load_and_validate


class DuplicateAgentError(ValueError):
    pass


@dataclass
class AgentSpec:
    id: str
    name: str
    version: str
    role: str
    division: str
    status: str
    description: str
    default_permission: ActionClass
    capabilities: Tuple[str, ...] = ()
    inputs: Tuple[dict, ...] = ()
    outputs: Tuple[dict, ...] = ()
    consumes_from: Tuple[str, ...] = ()
    evidence_requirements: Tuple[str, ...] = ()
    escalation_triggers: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    source: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict, source: Optional[str] = None) -> "AgentSpec":
        return cls(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            role=data["role"],
            division=data["division"],
            status=data["status"],
            description=data["description"],
            default_permission=ActionClass(data["default_permission"]),
            capabilities=tuple(data.get("capabilities", [])),
            inputs=tuple(data.get("inputs", [])),
            outputs=tuple(data.get("outputs", [])),
            consumes_from=tuple(data.get("consumes_from", [])),
            evidence_requirements=tuple(data.get("evidence_requirements", [])),
            escalation_triggers=tuple(data.get("escalation_triggers", [])),
            tags=tuple(data.get("tags", [])),
            source=source,
        )


class AgentRegistry:
    def __init__(self, specs: Optional[List[AgentSpec]] = None):
        self._by_id: Dict[str, AgentSpec] = {}
        for spec in specs or []:
            self.add(spec)

    def add(self, spec: AgentSpec) -> None:
        if spec.id in self._by_id:
            raise DuplicateAgentError(f"Duplicate agent id: {spec.id}")
        self._by_id[spec.id] = spec

    def get(self, agent_id: str) -> AgentSpec:
        return self._by_id[agent_id]

    def __contains__(self, agent_id: object) -> bool:
        return agent_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)

    def all(self) -> List[AgentSpec]:
        return list(self._by_id.values())

    def ids(self) -> List[str]:
        return list(self._by_id)

    def by_division(self, division: str) -> List[AgentSpec]:
        return [s for s in self._by_id.values() if s.division == division]

    def by_role(self, role: str) -> List[AgentSpec]:
        return [s for s in self._by_id.values() if s.role == role]

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "AgentRegistry":
        directory = directory or AGENT_SPECS_DIR
        registry = cls()
        for path in iter_spec_files(directory):
            data = load_and_validate(path, "agent_spec")
            registry.add(AgentSpec.from_dict(data, source=str(path)))
        return registry
