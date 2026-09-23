"""GROKBOT COMMERCE — master orchestrator foundation.

This package contains the control system for a multi-agent commerce platform.
The current phase performs no external actions, connects no production
credentials, and starts no autonomous processes.
"""
from __future__ import annotations

__version__ = "0.3.0"

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
