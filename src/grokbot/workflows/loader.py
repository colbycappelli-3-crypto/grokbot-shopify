"""Workflow loader.

A workflow is a directed acyclic graph of stages. The loader validates each
workflow against the schema, then verifies structural integrity: unique stage
ids, resolvable dependencies, and the absence of cycles. It also exposes a
deterministic topological execution order.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..resources import WORKFLOW_SPECS_DIR
from ..validation import iter_spec_files, load_and_validate

GATE_TYPES = ("validation_gate", "approval_gate")


class WorkflowError(ValueError):
    pass


@dataclass
class Stage:
    id: str
    name: str
    type: str
    agent: Optional[str] = None
    depends_on: Tuple[str, ...] = ()
    permission: Optional[str] = None
    produces: Tuple[str, ...] = ()
    validation: Optional[dict] = None
    approval: Optional[dict] = None

    @property
    def is_gate(self) -> bool:
        return self.type in GATE_TYPES


@dataclass
class WorkflowSpec:
    id: str
    name: str
    version: str
    division: str
    description: str
    stages: List[Stage]
    objective: Optional[str] = None
    source: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict, source: Optional[str] = None) -> "WorkflowSpec":
        stages = [
            Stage(
                id=s["id"],
                name=s["name"],
                type=s["type"],
                agent=s.get("agent"),
                depends_on=tuple(s.get("depends_on", [])),
                permission=s.get("permission"),
                produces=tuple(s.get("produces", [])),
                validation=s.get("validation"),
                approval=s.get("approval"),
            )
            for s in data["stages"]
        ]
        workflow = cls(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            division=data["division"],
            description=data["description"],
            stages=stages,
            objective=data.get("objective"),
            source=source,
        )
        workflow.validate_graph()
        return workflow

    def stage_map(self) -> Dict[str, Stage]:
        return {s.id: s for s in self.stages}

    def gates(self) -> List[Stage]:
        return [s for s in self.stages if s.is_gate]

    def validate_graph(self) -> None:
        seen = set()
        for stage in self.stages:
            if stage.id in seen:
                raise WorkflowError(f"{self.id}: duplicate stage id '{stage.id}'")
            seen.add(stage.id)
        for stage in self.stages:
            for dep in stage.depends_on:
                if dep == stage.id:
                    raise WorkflowError(f"{self.id}: stage '{stage.id}' depends on itself")
                if dep not in seen:
                    raise WorkflowError(
                        f"{self.id}: stage '{stage.id}' depends on unknown stage '{dep}'"
                    )
        # Cycle detection is performed by execution_order().
        self.execution_order()

    def execution_order(self) -> List[str]:
        """Return stage ids in a deterministic topological order."""
        smap = self.stage_map()
        indegree = {sid: 0 for sid in smap}
        adjacency: Dict[str, List[str]] = {sid: [] for sid in smap}
        for stage in self.stages:
            for dep in stage.depends_on:
                adjacency[dep].append(stage.id)
                indegree[stage.id] += 1

        ready = [sid for sid, deg in indegree.items() if deg == 0]
        heapq.heapify(ready)
        order: List[str] = []
        while ready:
            sid = heapq.heappop(ready)
            order.append(sid)
            for nxt in adjacency[sid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    heapq.heappush(ready, nxt)

        if len(order) != len(smap):
            remaining = sorted(set(smap) - set(order))
            raise WorkflowError(f"{self.id}: dependency cycle involving {remaining}")
        return order


def load_workflow(path: Path) -> WorkflowSpec:
    data = load_and_validate(Path(path), "workflow_spec")
    return WorkflowSpec.from_dict(data, source=str(path))


def load_all_workflows(directory: Optional[Path] = None) -> List[WorkflowSpec]:
    directory = directory or WORKFLOW_SPECS_DIR
    return [load_workflow(path) for path in iter_spec_files(directory)]
