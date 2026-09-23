"""Command-line interface for the GROKBOT control system.

Commands perform no external actions:

* ``grokbot validate`` — load and validate specs, gates, fixtures, and cross-references.
* ``grokbot plan <workflow>`` — print a dependency-ordered plan for a workflow.
* ``grokbot simulate <workflow> --fixture <id>`` — run an offline TEST/MOCK simulation.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .agents.registry import AgentRegistry
from .fixtures.loader import load_all_fixtures, load_fixture
from .gates.loader import load_validation_gates
from .orchestrator.engine import WorkflowSelectionError, build_runner
from .orchestrator.orchestrator import Orchestrator
from .policy.approval import load_default_policy
from .validation import SpecValidationError
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


def _gate_problems(workflows, gate_config) -> List[str]:
    known = set(gate_config["gates"])
    problems: List[str] = []
    for workflow in workflows:
        for stage in workflow.stages:
            gate_ids = list((stage.validation or {}).get("gate_ids") or [])
            for gate_id in gate_ids:
                if gate_id not in known:
                    problems.append(
                        f"workflow '{workflow.id}' stage '{stage.id}' references unknown gate '{gate_id}'"
                    )
    return problems


def _fixture_problems(fixtures, workflows) -> List[str]:
    known = {workflow.id for workflow in workflows}
    problems: List[str] = []
    for fixture in fixtures:
        if fixture["workflow_id"] not in known:
            problems.append(
                f"fixture '{fixture['fixture_id']}' references unknown workflow '{fixture['workflow_id']}'"
            )
        if fixture.get("data_classification") != "TEST_MOCK":
            problems.append(f"fixture '{fixture['fixture_id']}' is not marked TEST_MOCK")
    return problems


def cmd_validate(_args: argparse.Namespace) -> int:
    registry, workflows, policy = _load_all()
    try:
        gate_config = load_validation_gates()
        fixtures = load_all_fixtures()
    except SpecValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Agents:    {len(registry)} loaded and schema-valid")
    print(f"Workflows: {len(workflows)} loaded, DAGs acyclic")
    print(
        f"Policy:    v{policy.version}, default={policy.default_class.value}, "
        f"{len(policy.categories())} categories"
    )
    print(f"Gates:     v{gate_config['version']}, {len(gate_config['gates'])} configurable defaults")
    print(f"Fixtures:  {len(fixtures)} TEST/MOCK packets")
    problems = _cross_reference_problems(registry, workflows)
    problems.extend(_gate_problems(workflows, gate_config))
    problems.extend(_fixture_problems(fixtures, workflows))
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


def cmd_simulate(args: argparse.Namespace) -> int:
    try:
        fixture = load_fixture(args.fixture)
    except SpecValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    runner = build_runner()
    objective = args.objective or fixture["objective"]
    try:
        run = runner.open_opportunity(objective, workflow_id=args.workflow, fixture=fixture)
    except WorkflowSelectionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    runner.run(run)
    dossier = run.dossier or {}
    sections = dossier.get("sections") or {}
    print(f"Phase:     {run.phase}")
    print(f"Project:   {run.project.project_id}")
    print(f"Workflow:  {run.workflow.id}")
    print(f"Status:    {run.project.status}")
    print(f"Stopped:   {run.stop_reason}")
    print(f"Fixture:   {fixture['fixture_id']} ({fixture['data_classification']})")
    print(f"External actions performed: {len(run.external_actions_performed)}")
    print("\nJobs:")
    for stage_id, job in run.jobs.items():
        print(f"  - {job.job_id} [{job.status}] agent={job.agent_id} attempts={job.attempts}")
    print("\nGates:")
    for gate in run.gate_results:
        codes = ",".join(reason["code"] for reason in gate["reasons"] if reason.get("severity") == "fail") or "pass"
        print(f"  - {gate['gate_id']}: {'pass' if gate['passed'] else 'fail'} ({codes})")
    nxt = (sections.get("next_recommended_stage") or {}).get("content", {})
    print(f"\nNext recommended stage: {nxt.get('stage')}")
    unknowns = (sections.get("unknowns") or {}).get("content") or []
    print(f"Unknowns recorded: {len(unknowns)}")
    failed = (sections.get("failed_validation_criteria") or {}).get("content") or []
    print(f"Failed validation criteria: {len(failed)}")
    print(f"\n{dossier.get('banner', '')}")
    print("No external commerce action was performed. Workflow is offline.")
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

    simulate = sub.add_parser(
        "simulate",
        help="Run an offline Phase 2 workflow against a TEST/MOCK fixture.",
    )
    simulate.add_argument("workflow", help="Workflow id to simulate.")
    simulate.add_argument("--fixture", required=True, help="Fixture id, for example promising_pod.")
    simulate.add_argument("--objective", default=None)
    simulate.set_defaults(func=cmd_simulate)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
