"""GROKBOT COMMERCE — master orchestrator foundation.

This package contains the control-system foundation for an autonomous
multi-agent commerce platform. In this phase it intentionally performs no
external actions, connects to no production services, and starts no autonomous
processes.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .agents.registry import AgentRegistry, AgentSpec
from .orchestrator.orchestrator import Orchestrator, Plan, PlannedTask
from .policy.approval import ActionClass, ApprovalPolicy, load_default_policy
from .state.project_state import ProjectState
from .workflows.loader import WorkflowSpec, load_all_workflows, load_workflow

__all__ = [
    "__version__",
    "ActionClass",
    "ApprovalPolicy",
    "load_default_policy",
    "AgentRegistry",
    "AgentSpec",
    "WorkflowSpec",
    "load_workflow",
    "load_all_workflows",
    "ProjectState",
    "Orchestrator",
    "Plan",
    "PlannedTask",
]
