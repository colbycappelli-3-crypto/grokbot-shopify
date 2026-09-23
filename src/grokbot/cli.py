"""Command-line interface for the GROKBOT control system.

Commands perform no external actions:

* ``grokbot validate`` — load and validate specs, gates, fixtures, connectors, and packets.
* ``grokbot plan <workflow>`` — print a dependency-ordered plan for a workflow.
* ``grokbot simulate <workflow> --fixture <id>`` — run an offline TEST/MOCK simulation.
* ``grokbot research <workflow> --packet <id>`` — run read-only research and enqueue review.
* ``grokbot review`` — list, show, render, or decide a human review. Decisions do not execute.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .agents.registry import AgentRegistry
from .connectors.registry import ConnectorRegistry
from .fixtures.loader import load_all_fixtures, load_all_research_packets, load_fixture, load_research_packet
from .gates.loader import load_validation_gates
from .orchestrator.engine import WorkflowSelectionError, build_runner
from .orchestrator.orchestrator import Orchestrator
from .policy.approval import load_default_policy
from .review.queue import ReviewQueue, ReviewStateError, default_review_dir
from .review.surface import render_reviews, serve_reviews
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


def _research_problems(packets, workflows, connectors: ConnectorRegistry) -> List[str]:
    known = {workflow.id: workflow for workflow in workflows}
    problems: List[str] = []
    for packet in packets:
        workflow = known.get(packet["workflow_id"])
        if workflow is None:
            problems.append(
                f"research packet '{packet['packet_id']}' references unknown workflow '{packet['workflow_id']}'"
            )
        elif workflow.division != packet["division"]:
            problems.append(
                f"research packet '{packet['packet_id']}' division does not match workflow '{workflow.id}'"
            )
        for request in packet["connector_requests"]:
            spec = connectors.get(request["connector_id"])
            if spec is None:
                problems.append(
                    f"research packet '{packet['packet_id']}' references unknown connector '{request['connector_id']}'"
                )
                continue
            if request["operation"] not in spec["operations_allowed"]:
                problems.append(
                    f"research packet '{packet['packet_id']}' operation '{request['operation']}' is not allowed"
                )
            queries = (connectors.mocks.get(request["connector_id"]) or {}).get("queries") or {}
            if request["query_id"] not in queries:
                problems.append(
                    f"research packet '{packet['packet_id']}' query '{request['query_id']}' is not in the mock connector"
                )
    return problems


def cmd_validate(_args: argparse.Namespace) -> int:
    registry, workflows, policy = _load_all()
    try:
        gate_config = load_validation_gates()
        fixtures = load_all_fixtures()
        connectors = ConnectorRegistry.load()
        packets = load_all_research_packets()
    except (SpecValidationError, ValueError) as exc:
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
    print(f"Connectors:{len(connectors)} read-only/mock")
    print(f"Research:  {len(packets)} TEST/MOCK packets")
    problems = _cross_reference_problems(registry, workflows)
    problems.extend(_gate_problems(workflows, gate_config))
    problems.extend(_fixture_problems(fixtures, workflows))
    problems.extend(_research_problems(packets, workflows, connectors))
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


def _print_run(run, label: str) -> None:
    dossier = run.dossier or {}
    print(f"Phase:     {run.phase}")
    print(f"Project:   {run.project.project_id}")
    print(f"Workflow:  {run.workflow.id}")
    print(f"Status:    {run.project.status}")
    print(f"Stopped:   {run.stop_reason}")
    print(f"Source:    {label}")
    print(f"External actions performed: {len(run.external_actions_performed)}")
    if run.review_item_id:
        print(f"Review:    {run.review_item_id}")
    print(f"\n{dossier.get('banner', '')}")
    print("No external commerce action was performed.")


def cmd_research(args: argparse.Namespace) -> int:
    try:
        packet = load_research_packet(args.packet)
    except SpecValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    runner = build_runner()
    queue = ReviewQueue(args.queue)
    objective = args.objective or packet["objective"]
    try:
        run = runner.open_opportunity(objective, workflow_id=args.workflow, fixture=packet)
    except WorkflowSelectionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    runner.run(run, review_queue=queue)
    _print_run(run, f"{packet['packet_id']} ({packet['data_classification']})")
    return 0


def _queue(args: argparse.Namespace) -> ReviewQueue:
    return ReviewQueue(args.queue)


def cmd_review_list(args: argparse.Namespace) -> int:
    try:
        items = _queue(args).list_items()
    except ReviewStateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not items:
        print("No review items.")
        return 0
    for item in items:
        print(f"{item['review_id']}  {item['status']}  {item['workflow_id']}  {item['project_id']}")
    return 0


def cmd_review_show(args: argparse.Namespace) -> int:
    try:
        item = _queue(args).get(args.review_id)
    except ReviewStateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Review:    {item['review_id']}")
    print(f"Status:    {item['status']}")
    print(f"Workflow:  {item['workflow_id']}")
    print(f"Project:   {item['project_id']}")
    print(f"Banner:    {item['banner']}")
    print(f"Summary:   {item['summary']}")
    print(f"Unknowns:  {len(item['unknowns'])}")
    print(f"External actions performed: {len(item['consequential_actions_performed'])}")
    decision = item.get("decision") or {}
    if decision:
        print(f"Decision:  {decision.get('decision')} executed_external_action={decision.get('executed_external_action')}")
    return 0


def cmd_review_render(args: argparse.Namespace) -> int:
    try:
        page = render_reviews(_queue(args))
    except ReviewStateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(page, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(page)
    return 0


def cmd_review_serve(args: argparse.Namespace) -> int:
    try:
        queue = _queue(args)
        queue.list_items()
    except ReviewStateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    server = serve_reviews(queue, host=args.host, port=args.port)
    print(f"Read-only review page at http://{args.host}:{server.server_address[1]}/")
    print("POST is rejected. This server does not execute decisions. Ctrl-C stops it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def cmd_review_decide(args: argparse.Namespace) -> int:
    queue = _queue(args)
    try:
        item = queue.decide(args.review_id, args.decision, note=args.note or "", decided_by=args.by)
    except (ReviewStateError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    recorded = item["decision"]
    print(f"Review:    {item['review_id']}")
    print(f"Status:    {item['status']}")
    print(f"Decision:  {recorded['decision']}")
    print(f"Executed external action: {recorded['executed_external_action']}")
    if recorded.get("blocked_reason"):
        print(f"Blocked:   {recorded['blocked_reason']}")
    print("No purchase, publication, supplier contact, message, order, or refund was performed.")
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

    research = sub.add_parser(
        "research",
        help="Run a read-only research workflow and enqueue human review.",
    )
    research.add_argument("workflow", help="Research workflow id.")
    research.add_argument("--packet", required=True, help="Research packet id.")
    research.add_argument("--objective", default=None)
    research.add_argument("--queue", default=default_review_dir(), help="Review queue directory.")
    research.set_defaults(func=cmd_research)

    review = sub.add_parser("review", help="Inspect or decide a human review. Decisions do not execute.")
    review_sub = review.add_subparsers(dest="review_command", required=True)

    review_list = review_sub.add_parser("list", help="List queued reviews.")
    review_list.add_argument("--queue", default=default_review_dir())
    review_list.set_defaults(func=cmd_review_list)

    review_show = review_sub.add_parser("show", help="Show one review.")
    review_show.add_argument("review_id")
    review_show.add_argument("--queue", default=default_review_dir())
    review_show.set_defaults(func=cmd_review_show)

    review_render = review_sub.add_parser("render", help="Render the read-only HTML review page.")
    review_render.add_argument("--queue", default=default_review_dir())
    review_render.add_argument("--output", default=None)
    review_render.set_defaults(func=cmd_review_render)

    review_serve = review_sub.add_parser("serve", help="Serve the read-only HTML review page on localhost.")
    review_serve.add_argument("--queue", default=default_review_dir())
    review_serve.add_argument("--host", default="127.0.0.1")
    review_serve.add_argument("--port", type=int, default=8765)
    review_serve.set_defaults(func=cmd_review_serve)

    review_decide = review_sub.add_parser("decide", help="Record a decision without executing it.")
    review_decide.add_argument("review_id")
    review_decide.add_argument("--decision", required=True, choices=["approved", "denied", "research_requested"])
    review_decide.add_argument("--note", default="")
    review_decide.add_argument("--by", default="human_owner")
    review_decide.add_argument("--queue", default=default_review_dir())
    review_decide.set_defaults(func=cmd_review_decide)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
