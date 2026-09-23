"""Command-line interface for the GROKBOT control system.

Commands are read-only / planning-only and perform no external actions:

* ``grokbot validate`` — load and validate all specs, config, and cross-references.
* ``grokbot plan <workflow>`` — print a dependency-ordered plan for a workflow.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .agents.registry import AgentRegistry
from .orchestrator.orchestrator import Orchestrator
from .policy.approval import load_default_policy
from .workflows.loader import load_all_workflows


def _load_all():
    registry = AgentRegistry.load()
    workflows = load_all_workflows()
    policy = load_default_policy()
    return registry, workflows, policy


def _cross_reference_problems(registry: AgentRegistry, workflows) -> List[str]:
    problems: List[str] = []
    for workflow in workflows:
        for stage in workflow.stages:
            if stage.agent and stage.agent not in registry:
                problems.append(
                    f"workflow '{workflow.id}' stage '{stage.id}' references unknown agent '{stage.agent}'"
                )
    return problems


def cmd_validate(_args: argparse.Namespace) -> int:
    registry, workflows, policy = _load_all()
    print(f"Agents:    {len(registry)} loaded and schema-valid")
    print(f"Workflows: {len(workflows)} loaded, DAGs acyclic")
    print(
        f"Policy:    v{policy.version}, default={policy.default_class.value}, "
        f"{len(policy.categories())} categories"
    )
    problems = _cross_reference_problems(registry, workflows)
    if problems:
        print("\nCross-reference problems:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nAll specifications valid. No external actions performed.")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    registry, workflows, policy = _load_all()
    orchestrator = Orchestrator(registry, policy, workflows=workflows)
    try:
        plan = orchestrator.plan(args.objective, args.workflow)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        available = ", ".join(sorted(w.id for w in workflows)) or "(none)"
        print(f"Available workflows: {available}", file=sys.stderr)
        return 2

    print(f"Plan for workflow '{plan.workflow_id}' (division: {plan.division})")
    print(f"Objective: {plan.objective}\n")
    for task in plan.tasks:
        extras = []
        if task.agent_role:
            extras.append(task.agent_role)
        if task.action_class:
            extras.append(task.action_class)
        if task.requires_approval:
            extras.append("OWNER APPROVAL")
        suffix = f"  [{', '.join(extras)}]" if extras else ""
        print(f"  {task.order + 1:>2}. ({task.stage_type}) {task.stage_name}{suffix}")

    if plan.warnings:
        print("\nWarnings:")
        for warning in plan.warnings:
            print(f"  - {warning}")
    if plan.requires_owner_approval:
        print("\nThis workflow contains actions/gates that REQUIRE human owner approval.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grokbot",
        description="GROKBOT COMMERCE control-system CLI (no external actions).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate all specs and configuration.")
    validate.set_defaults(func=cmd_validate)

    plan = sub.add_parser("plan", help="Produce a dependency-ordered plan for a workflow.")
    plan.add_argument("workflow", help="Workflow id to plan.")
    plan.add_argument("--objective", default="(unspecified objective)")
    plan.set_defaults(func=cmd_plan)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
