"""GROKBOT master orchestrator.

``plan`` remains the dependency-ordered planning view from Phase 1. Offline
execution of a workflow lives in ``WorkflowRunner`` and is reached through
``open_opportunity`` / ``run_opportunity``. Execution reads specs and TEST/MOCK
fixtures only. It does not contact external services or perform consequential
actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from ..agents.registry import AgentRegistry
from ..policy.approval import ActionClass, ApprovalPolicy
from ..state.project_state import ProjectState
from ..workflows.loader import WorkflowSpec

WorkflowRef = Union[str, WorkflowSpec]


@dataclass
class PlannedTask:
    order: int
    stage_id: str
    stage_name: str
    stage_type: str
    agent_id: Optional[str]
    agent_role: Optional[str]
    action_class: Optional[str]
    requires_approval: bool
    is_gate: bool
    depends_on: Tuple[str, ...]
    notes: Tuple[str, ...] = ()


@dataclass
class Plan:
    objective: str
    workflow_id: str
    division: str
    tasks: List[PlannedTask]
    warnings: List[str] = field(default_factory=list)

    @property
    def approval_gates(self) -> List[PlannedTask]:
        return [t for t in self.tasks if t.stage_type == "approval_gate"]

    @property
    def prohibited_tasks(self) -> List[PlannedTask]:
        return [t for t in self.tasks if t.action_class == ActionClass.PROHIBITED.value]

    @property
    def requires_owner_approval(self) -> bool:
        return any(
            t.requires_approval or t.stage_type == "approval_gate" for t in self.tasks
        )


class Orchestrator:
    def __init__(
        self,
        registry: AgentRegistry,
        policy: ApprovalPolicy,
        *,
        workflows: Optional[List[WorkflowSpec]] = None,
    ):
        self.registry = registry
        self.policy = policy
        self.workflows: Dict[str, WorkflowSpec] = {w.id: w for w in (workflows or [])}

    def register_workflow(self, workflow: WorkflowSpec) -> None:
        self.workflows[workflow.id] = workflow

    def _resolve(self, workflow: WorkflowRef) -> WorkflowSpec:
        if isinstance(workflow, WorkflowSpec):
            return workflow
        if workflow not in self.workflows:
            raise KeyError(f"Unknown workflow: {workflow}")
        return self.workflows[workflow]

    def plan(self, objective: str, workflow: WorkflowRef) -> Plan:
        workflow = self._resolve(workflow)
        order = workflow.execution_order()
        stage_map = workflow.stage_map()
        tasks: List[PlannedTask] = []
        warnings: List[str] = []

        for index, stage_id in enumerate(order):
            stage = stage_map[stage_id]
            agent_role: Optional[str] = None
            action_class: Optional[str] = None
            requires_approval = stage.type == "approval_gate"
            notes: List[str] = []

            if stage.agent:
                if stage.agent in self.registry:
                    agent_role = self.registry.get(stage.agent).role
                else:
                    warnings.append(
                        f"stage '{stage_id}' references unknown agent '{stage.agent}'"
                    )
                    notes.append("unknown-agent")

            if stage.type == "action" and stage.permission:
                declared = ActionClass(stage.permission)
                action_class = declared.value
                if declared is ActionClass.PROHIBITED:
                    warnings.append(f"stage '{stage_id}' declares a PROHIBITED action")
                    notes.append("prohibited")
                elif declared is ActionClass.APPROVAL_REQUIRED:
                    requires_approval = True

            tasks.append(
                PlannedTask(
                    order=index,
                    stage_id=stage_id,
                    stage_name=stage.name,
                    stage_type=stage.type,
                    agent_id=stage.agent,
                    agent_role=agent_role,
                    action_class=action_class,
                    requires_approval=requires_approval,
                    is_gate=stage.is_gate,
                    depends_on=stage.depends_on,
                    notes=tuple(notes),
                )
            )

        return Plan(
            objective=objective,
            workflow_id=workflow.id,
            division=workflow.division,
            tasks=tasks,
            warnings=warnings,
        )

    def execution_runner(self):
        """Return the offline runner that executes workflows for this orchestrator."""
        from .engine import WorkflowRunner

        return WorkflowRunner(self.registry, self.policy, list(self.workflows.values()))

    def open_opportunity(self, objective: str, **kwargs):
        return self.execution_runner().open_opportunity(objective, **kwargs)

    def run_opportunity(self, run, faults=None):
        return self.execution_runner().run(run, faults=faults)

    def new_project(self, project_id: str, name: str, workflow: WorkflowRef) -> ProjectState:
        workflow = self._resolve(workflow)
        return ProjectState.new(
            project_id=project_id,
            name=name,
            division=workflow.division,
            workflow_id=workflow.id,
            stages=[s.id for s in workflow.stages],
        )
