"""Offline workflow runner.

The runner delegates jobs, enforces dependencies, preserves evidence, evaluates
gates, and stops at human review. It does not contact external services or
execute consequential actions.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from ..agents.registry import AgentRegistry
from ..agents.runtime import default_runtimes
from ..audit.log import redact
from ..agents.runtime.common import FIXTURE_AGENTS
from ..clock import utc_now
from ..dossier.builder import build_dossier
from ..evidence.ledger import EvidenceError, record_from_dict
from ..gates.evaluator import build_gate_context, evaluate_gate, select_on_fail
from ..gates.loader import load_validation_gates
from ..phase import CONSEQUENTIAL_ACTION_CATEGORIES, NON_EXECUTABLE_AGENTS, PHASE
from ..phase import DISCOVERY_WORKFLOWS
from ..policy.approval import ActionClass, ApprovalPolicy
from ..protocol.knowledge import enforce_structured_output, iter_claims
from ..protocol.models import Job, RetryPolicy, make_result
from ..state.project_state import ProjectState
from ..validation import SpecValidationError
from ..workflows.loader import WorkflowSpec
from .run import OpportunityRun

AGENT_CATEGORY = {
    "trend_discovery_agent": "trend_discovery",
    "market_research_agent": "market_research",
    "product_validation_agent": "product_validation",
    "unit_economics_agent": "unit_economics_analysis",
    "compliance_ip_screening_agent": "ip_screening",
    "supplier_research_agent": "supplier_research",
    "opportunity_dossier_agent": "market_research",
    "shopify_store_builder_agent": "launch_store",
    "customer_service_agent": "send_customer_message",
    "research_connector_agent": "commerce_research_read",
    "pod_product_draft_agent": "product_design_draft",
    "listing_draft_agent": "merchandising_plan_draft",
    "service_research_agent": "market_research",
    "service_workflow_agent": "quality_assurance_review",
    "service_communication_draft_agent": "prepare_customer_message_draft",
}

_STOP_STATUS = {
    "human_review": "awaiting_approval",
    "request_more_research": "on_hold",
    "reject": "rejected",
    "escalate": "on_hold",
    "halt": "on_hold",
    "terminal_failure": "on_hold",
    "phase_blocked": "on_hold",
    "dependency_deadlock": "on_hold",
}


class WorkflowSelectionError(ValueError):
    pass


class FaultScript:
    def __init__(self, script: Optional[Dict[str, List[dict]]] = None):
        self._queues = {key: list(value) for key, value in (script or {}).items()}

    def consume(self, stage_id: str) -> Optional[dict]:
        queue = self._queues.get(stage_id) or []
        if not queue:
            return None
        return queue.pop(0)


class WorkflowRunner:
    def __init__(
        self,
        registry: AgentRegistry,
        policy: ApprovalPolicy,
        workflows: List[WorkflowSpec],
        gate_config: Optional[dict] = None,
        runtimes: Optional[dict] = None,
    ):
        self.registry = registry
        self.policy = policy
        self.workflows = {workflow.id: workflow for workflow in workflows}
        self.gate_config = gate_config or load_validation_gates()
        self.runtimes = default_runtimes()
        if runtimes:
            self.runtimes.update(runtimes)

    def identify_workflow(
        self,
        *,
        workflow_id: Optional[str] = None,
        division: Optional[str] = None,
    ) -> WorkflowSpec:
        if workflow_id:
            if workflow_id not in self.workflows:
                known = ", ".join(sorted(self.workflows)) or "(none)"
                raise WorkflowSelectionError(f"Unknown workflow '{workflow_id}'. Known: {known}")
            return self.workflows[workflow_id]
        if division in DISCOVERY_WORKFLOWS:
            return self.identify_workflow(workflow_id=DISCOVERY_WORKFLOWS[division])
        raise WorkflowSelectionError(
            "Pass workflow_id or a supported division (print_on_demand, us_dropshipping)."
        )

    def open_opportunity(
        self,
        objective: str,
        *,
        workflow_id: Optional[str] = None,
        division: Optional[str] = None,
        name: Optional[str] = None,
        fixture: Optional[dict] = None,
        project_id: Optional[str] = None,
    ) -> OpportunityRun:
        fixture_workflow = (fixture or {}).get("workflow_id")
        if workflow_id and fixture_workflow and workflow_id != fixture_workflow:
            raise WorkflowSelectionError(
                f"Requested workflow '{workflow_id}' does not match fixture workflow '{fixture_workflow}'."
            )
        workflow = self.identify_workflow(
            workflow_id=workflow_id or fixture_workflow,
            division=division or (fixture or {}).get("division"),
        )
        project_id = project_id or f"opp-{uuid.uuid4().hex[:12]}"
        project_name = (name or (fixture or {}).get("niche_hypothesis") or objective)[:180]
        project = ProjectState.new(
            project_id=project_id,
            name=project_name,
            division=workflow.division,
            workflow_id=workflow.id,
            stages=[stage.id for stage in workflow.stages],
        )
        run = OpportunityRun(
            project=project,
            workflow=workflow,
            objective=objective,
            fixture=fixture,
            gate_config=self.gate_config,
        )
        project.set_status("researching")
        run.audit.record(
            "project_created",
            project_id=project.project_id,
            workflow_id=workflow.id,
            division=workflow.division,
            objective=objective,
            phase=PHASE,
            fixture_id=(fixture or {}).get("fixture_id"),
        )
        self._ingest_evidence(run)
        self._create_jobs(run)
        self._decide(run, "grokbot", f"Opened offline opportunity on workflow {workflow.id}.")
        return run

    def run(
        self,
        run: OpportunityRun,
        faults: Optional[Dict[str, List[dict]]] = None,
        review_queue: Optional[Any] = None,
    ) -> OpportunityRun:
        script = FaultScript(faults)
        while not run.stopped:
            stage = self._next_stage(run)
            if stage is None:
                if not run.stopped and any(run.stage_status(stage.id) == "pending" for stage in run.workflow.stages):
                    self._stop(run, "dependency_deadlock")
                break
            if stage.type == "validation_gate":
                self._evaluate_gate(run, stage)
            elif stage.type == "approval_gate":
                self._stop_for_human_review(run, stage)
            else:
                self._execute_job(run, stage, script)
        self._finalize(run, review_queue)
        return run

    def attempt_action(self, run: OpportunityRun, category: str) -> dict:
        """Guard a consequential or prohibited action. Phase 2 never executes it."""
        decision = self.policy.classify(category)
        reasons = []
        if decision.prohibited:
            reasons.append(
                {
                    "code": "prohibited_action",
                    "message": f"{category} is PROHIBITED and cannot be relaxed.",
                }
            )
        consequential = category in CONSEQUENTIAL_ACTION_CATEGORIES or decision.requires_approval
        if consequential:
            reasons.append(
                {
                    "code": "phase_2_offline_no_consequential_actions",
                    "message": "Phase 2 performs no consequential external action.",
                }
            )
        if decision.requires_approval:
            reasons.append(
                {
                    "code": "approval_required",
                    "message": "This category requires human approval. Approval would still not execute it in Phase 2.",
                }
            )
        blocked = bool(reasons)
        if decision.allowed_autonomously and not consequential:
            reasons.append(
                {
                    "code": "autonomous_offline_only",
                    "message": "Category is autonomous and has no external executor in Phase 2.",
                }
            )
        result = {
            "category": category,
            "action_class": decision.action_class.value,
            "executed": False,
            "blocked": blocked,
            "reasons": reasons,
            "phase": PHASE,
        }
        event = "action_blocked" if blocked else "decision_recorded"
        run.audit.record(
            event,
            project_id=run.project.project_id,
            category=category,
            executed=False,
            reasons=reasons,
        )
        return result

    def record_simulated_approval(
        self,
        run: OpportunityRun,
        decision: str,
        approver: str = "human_owner_simulation",
    ) -> dict:
        """Record an approval decision without performing an external action."""
        if decision not in {"approved", "denied"}:
            raise ValueError("Approval decision must be 'approved' or 'denied'.")
        if decision == "approved":
            blocked = self._approval_block_reason(run)
            if blocked:
                self._decide(
                    run,
                    "grokbot",
                    f"Simulated approval blocked: {blocked}.",
                    rationale="Unresolved screening prevents automatic approval. No external action was performed.",
                )
                run.audit.record(
                    "approval_decision",
                    project_id=run.project.project_id,
                    decision="blocked",
                    blocked_reason=blocked,
                    approver=approver,
                    executed_external_action=False,
                )
                return {
                    "decision": "blocked",
                    "blocked_reason": blocked,
                    "executed_external_action": False,
                    "phase": PHASE,
                }
        if not run.pending_approval_action:
            return {
                "decision": "not_recorded",
                "blocked_reason": "no_pending_approval",
                "executed_external_action": False,
                "phase": PHASE,
            }
        run.project.resolve_approval(run.pending_approval_action, decision, approver)
        run.project.set_status("approved" if decision == "approved" else "on_hold")
        self._decide(
            run,
            approver,
            f"Simulated human review decision: {decision}.",
            rationale="Phase 2 records the decision and does not execute post-approval actions.",
        )
        run.audit.record(
            "approval_decision",
            project_id=run.project.project_id,
            decision=decision,
            approver=approver,
            action=run.pending_approval_action,
            executed_external_action=False,
        )
        if run.review_packet is not None:
            run.review_packet["decision"] = decision
            run.review_packet["execution"] = "not_performed"
        return {
            "decision": decision,
            "blocked_reason": None,
            "executed_external_action": False,
            "phase": PHASE,
        }

    def propose_consequential_action(self, run: OpportunityRun, store: Any, category: str, summary: str) -> dict:
        """Present one consequential action to the human owner. Nothing is executed."""
        classification = (run.fixture or {}).get("data_classification")
        item = store.propose(
            policy=self.policy,
            project_id=run.project.project_id,
            workflow_id=run.workflow.id,
            division=run.workflow.division,
            category=category,
            summary=summary,
            screening_block=self._approval_block_reason(run),
            data_classification=classification if classification in {"TEST_MOCK", "UNSOURCED"} else "UNSOURCED",
        )
        run.audit.record(
            "action_proposed",
            project_id=run.project.project_id,
            proposal_id=item["proposal_id"],
            category=category,
            gate_state=item["gate_state"],
            block_reason=item["block_reason"],
            executed_external_action=False,
        )
        self._decide(
            run,
            "grokbot",
            f"Proposed {category} for an explicit human decision.",
            rationale=summary,
        )
        return item

    def decide_consequential_action(
        self,
        run: OpportunityRun,
        store: Any,
        proposal_id: str,
        decision: str,
        note: str = "",
        decided_by: str = "human_owner",
    ) -> dict:
        """Record approve or reject. Only a clear approval advances to execution_withheld."""
        screening = self._approval_block_reason(run) if decision == "approved" else None
        item = store.decide(
            proposal_id,
            decision,
            note=note,
            decided_by=decided_by,
            screening_block=screening,
        )
        run.audit.record(
            "action_decision",
            project_id=run.project.project_id,
            proposal_id=proposal_id,
            category=item["category"],
            decision=item["decision"]["decision"],
            gate_state=item["gate_state"],
            advanced=item["advanced"],
            executed_external_action=False,
        )
        if item["advanced"]:
            run.audit.record(
                "gate_advanced",
                project_id=run.project.project_id,
                proposal_id=proposal_id,
                category=item["category"],
                next_gated_state=item["next_gated_state"],
                executed_external_action=False,
            )
        self._decide(
            run,
            decided_by,
            f"Action proposal {proposal_id} decision: {item['decision']['decision']}.",
            rationale="The decision record does not execute the action.",
        )
        return item

    def release_consequential_action(self, run: OpportunityRun, store: Any, proposal_id: str) -> dict:
        """Move an approved action to the execution gate and withhold the external effect."""
        result = store.release(proposal_id)
        run.audit.record(
            "execution_withheld",
            project_id=run.project.project_id,
            proposal_id=proposal_id,
            category=result["category"],
            gate_state=result["gate_state"],
            code=result["code"],
            executed=False,
        )
        run.audit.record(
            "action_blocked",
            project_id=run.project.project_id,
            category=result["category"],
            executed=False,
            reasons=[{"code": result["code"], "message": result["message"]}],
        )
        if result["executed"] or result["external_effects"]:
            raise RuntimeError("Phase 4 invariant failed: a consequential action was executed.")
        return result

    # ---- setup -----------------------------------------------------------------
    def _ingest_evidence(self, run: OpportunityRun) -> None:
        if not run.fixture:
            return
        for raw in run.fixture.get("evidence") or []:
            record = record_from_dict(raw)
            run.evidence.add(record)
            self._audit_evidence(run, record)
            key = f"evidence:{record.evidence_id}"
            if record.verification_status == "verified":
                run.project.record_evidence(
                    key,
                    value={
                        "claim_supported": record.claim_supported,
                        "source_type": record.source_type,
                        "epistemic_note": "TEST/MOCK evidence",
                    },
                    sources=[record.source_reference],
                    verified=True,
                )
            else:
                run.project.record_evidence(key)

    def _create_jobs(self, run: OpportunityRun) -> None:
        for stage in run.workflow.stages:
            if stage.type != "action":
                continue
            if not stage.agent or stage.agent not in self.registry:
                raise WorkflowSelectionError(
                    f"Workflow '{run.workflow.id}' stage '{stage.id}' has no registered agent."
                )
            agent = self.registry.get(stage.agent)
            job = Job(
                job_id=f"job-{stage.id}",
                project_id=run.project.project_id,
                workflow_id=run.workflow.id,
                agent_id=stage.agent,
                objective=run.objective,
                required_inputs=[
                    {"name": item["name"], "type": item["type"]}
                    for item in agent.inputs
                    if item.get("required", False)
                ],
                supplied_inputs={},
                dependencies=list(stage.depends_on),
                status="pending",
                permission_class=stage.permission or agent.default_permission.value,
                created_at=utc_now(),
                evidence_requirements=list(agent.evidence_requirements),
                expected_output_schema={
                    "fields": [{"name": item["name"], "type": item["type"]} for item in agent.outputs]
                },
                retry_policy=RetryPolicy(),
                stage_id=stage.id,
                attempts=0,
            )
            job.validate()
            run.jobs[stage.id] = job
            run.audit.record(
                "job_created",
                project_id=run.project.project_id,
                job_id=job.job_id,
                stage_id=stage.id,
                agent_id=job.agent_id,
                permission_class=job.permission_class,
                dependencies=job.dependencies,
            )

    # ---- loop ------------------------------------------------------------------
    def _next_stage(self, run: OpportunityRun):
        stage_map = run.workflow.stage_map()
        for stage_id in run.workflow.execution_order():
            status = run.stage_status(stage_id)
            if status in {"passed", "failed", "skipped", "blocked", "awaiting_approval"}:
                continue
            stage = stage_map[stage_id]
            dep_status = [run.stage_status(dep) for dep in stage.depends_on]
            if any(item in {"failed", "skipped", "blocked"} for item in dep_status):
                self._mark_skipped(run, stage, "dependency_not_passed")
                continue
            if any(item != "passed" for item in dep_status):
                return None
            return stage
        return None

    def _execute_job(self, run: OpportunityRun, stage, script: FaultScript) -> None:
        job = run.jobs[stage.id]
        blocked = self._preflight(stage, job)
        if blocked:
            result = make_result(
                job,
                status="failed",
                recommended_next_action="stop",
                errors=[blocked],
            )
            reason = "phase_blocked" if blocked["code"] == "phase_blocked" else "terminal_failure"
            self._fail_terminal(run, stage, job, result, stop_reason=reason)
            return
        job.supplied_inputs = self._collect_inputs(run, stage)
        job.attempts += 1
        job.status = "in_progress"
        job.validate()
        run.project.update_stage(stage.id, "in_progress")
        run.audit.record(
            "job_assigned",
            project_id=run.project.project_id,
            job_id=job.job_id,
            stage_id=stage.id,
            agent_id=job.agent_id,
            attempt=job.attempts,
        )
        fault = script.consume(stage.id)
        if fault:
            result = make_result(
                job,
                status="failed",
                recommended_next_action="retry" if fault.get("retryable") else "stop",
                errors=[
                    {
                        "code": fault["code"],
                        "message": fault.get("message", fault["code"]),
                        "retryable": bool(fault.get("retryable", False)),
                    }
                ],
            )
        else:
            result = self._invoke(run, job)
        if result.status == "completed":
            try:
                self._ingest_output_evidence(run, result.structured_output)
            except EvidenceError as exc:
                result = make_result(
                    job,
                    status="failed",
                    recommended_next_action="stop",
                    errors=[
                        {
                            "code": "evidence_rejected",
                            "message": str(redact(str(exc)))[:500],
                            "retryable": False,
                        }
                    ],
                )
        if result.status != "completed":
            self._handle_failure(run, stage, job, result)
            return
        enforced, flags = enforce_structured_output(result.structured_output, run.evidence.as_index())
        result.structured_output = enforced
        result.validation_flags = list(dict.fromkeys([*result.validation_flags, *flags]))
        cited = [
            evidence_id
            for claim_item in iter_claims(enforced)
            for evidence_id in (claim_item.get("evidence_ids") or [])
        ]
        result.evidence = list(dict.fromkeys([*result.evidence, *cited]))
        result.validate()
        run.outputs[stage.id] = enforced
        run.results[stage.id] = result
        job.status = "completed"
        job.validate()
        run.project.update_stage(stage.id, "passed")
        self._mirror_output(run, enforced)
        run.audit.record(
            "job_completed",
            project_id=run.project.project_id,
            job_id=job.job_id,
            stage_id=stage.id,
            agent_id=job.agent_id,
            validation_flags=result.validation_flags,
            recommended_next_action=result.recommended_next_action,
        )

    def _invoke(self, run: OpportunityRun, job: Job):
        runtime = self.runtimes[job.agent_id]
        try:
            result = runtime.run(job, run)
            result.validate()
            return result
        except SpecValidationError as exc:
            return make_result(
                job,
                status="failed",
                recommended_next_action="stop",
                errors=[
                    {
                        "code": "schema_violation",
                        "message": str(redact(str(exc)))[:500],
                        "retryable": False,
                    }
                ],
            )
        except Exception as exc:
            return make_result(
                job,
                status="failed",
                recommended_next_action="stop",
                errors=[
                    {
                        "code": "terminal_agent_error",
                        "message": str(redact(f"{type(exc).__name__}: {exc}"))[:500],
                        "retryable": False,
                    }
                ],
            )

    def _handle_failure(self, run: OpportunityRun, stage, job: Job, result) -> None:
        run.results[stage.id] = result
        if self._retryable(job, result.errors):
            job.status = "retrying"
            job.validate()
            run.project.update_stage(stage.id, "pending", notes="retry_scheduled")
            run.audit.record(
                "job_failed",
                project_id=run.project.project_id,
                job_id=job.job_id,
                stage_id=stage.id,
                agent_id=job.agent_id,
                attempt=job.attempts,
                will_retry=True,
                errors=result.errors,
            )
            run.audit.record(
                "retry_scheduled",
                project_id=run.project.project_id,
                job_id=job.job_id,
                stage_id=stage.id,
                attempt=job.attempts,
                max_attempts=job.retry_policy.max_attempts,
            )
            return
        self._fail_terminal(run, stage, job, result, stop_reason="terminal_failure")

    def _fail_terminal(self, run: OpportunityRun, stage, job: Job, result, stop_reason: str) -> None:
        run.results[stage.id] = result
        job.status = "failed"
        job.validate()
        code = result.errors[0]["code"] if result.errors else "failed"
        run.project.update_stage(stage.id, "failed" if stop_reason == "terminal_failure" else "blocked", notes=code)
        run.audit.record(
            "job_failed",
            project_id=run.project.project_id,
            job_id=job.job_id,
            stage_id=stage.id,
            agent_id=job.agent_id,
            attempt=job.attempts,
            will_retry=False,
            errors=result.errors,
        )
        if stop_reason == "phase_blocked" or code in {"prohibited_action", "phase_blocked"}:
            run.audit.record(
                "action_blocked",
                project_id=run.project.project_id,
                stage_id=stage.id,
                agent_id=job.agent_id,
                reasons=result.errors,
                executed=False,
            )
        self._decide(run, "grokbot", f"Job {job.job_id} failed terminally ({code}).")
        self._stop(run, stop_reason, stage_id=stage.id, error_code=code)

    def _evaluate_gate(self, run: OpportunityRun, stage) -> None:
        run.project.set_status("validating")
        context = build_gate_context(run)
        gate_ids = list((stage.validation or {}).get("gate_ids") or [])
        if gate_ids:
            evaluations = [evaluate_gate(gate_id, context, run.gate_config) for gate_id in gate_ids]
        else:
            evaluations = [
                {
                    "gate_id": stage.id,
                    "passed": False,
                    "applicable": True,
                    "reasons": [
                        {
                            "code": "gate_ids_not_configured",
                            "message": "Validation gate has no configured gate_ids and fails closed.",
                            "severity": "fail",
                        }
                    ],
                }
            ]
        run.gate_results.extend(evaluations)
        for evaluation in evaluations:
            run.audit.record(
                "validation_gate_evaluated",
                project_id=run.project.project_id,
                stage_id=stage.id,
                gate_id=evaluation["gate_id"],
                passed=evaluation["passed"],
                reasons=evaluation["reasons"],
            )
        if all(evaluation["passed"] for evaluation in evaluations):
            run.project.update_stage(stage.id, "passed")
            self._decide(run, "grokbot", f"Validation gate {stage.id} passed.")
            return
        on_fail = select_on_fail(
            (stage.validation or {}).get("on_fail", "halt"),
            evaluations,
            context.get("validation_outcome"),
        )
        failed_reasons = [
            reason
            for evaluation in evaluations
            for reason in evaluation["reasons"]
            if reason.get("severity") == "fail"
        ]
        run.project.update_stage(stage.id, "failed", notes=on_fail)
        self._decide(
            run,
            "grokbot",
            f"Validation gate {stage.id} failed ({on_fail}).",
            rationale="; ".join(reason["code"] for reason in failed_reasons),
        )
        if on_fail == "escalate":
            run.project.escalate(
                "Validation gate escalated: " + ", ".join(reason["code"] for reason in failed_reasons)
            )
        self._stop(run, on_fail, stage_id=stage.id, reasons=failed_reasons)

    def _stop_for_human_review(self, run: OpportunityRun, stage) -> None:
        description = (stage.approval or {}).get("description") or stage.name
        action = f"human_review:{run.workflow.id}"
        run.pending_approval_action = action
        run.project.request_approval(action, ActionClass.APPROVAL_REQUIRED)
        run.project.update_stage(stage.id, "awaiting_approval", notes=description)
        run.audit.record(
            "approval_requested",
            project_id=run.project.project_id,
            action=action,
            stage_id=stage.id,
            approver="human_owner",
        )
        self._decide(run, "grokbot", f"Stopped for human review at {stage.id}.", rationale=description)
        self._stop(run, "human_review", stage_id=stage.id)

    def _finalize(self, run: OpportunityRun, review_queue: Optional[Any] = None) -> None:
        if run.stopped:
            for stage in run.workflow.stages:
                if run.stage_status(stage.id) == "pending":
                    run.project.update_stage(stage.id, "skipped", notes=f"skipped_after:{run.stop_reason}")
                job = run.jobs.get(stage.id)
                if job is not None and job.status in {"pending", "retrying"}:
                    job.status = "blocked"
                    job.validate()
        run.dossier = build_dossier(run)
        if "compile_dossier" in run.outputs:
            run.outputs["compile_dossier"]["final_dossier_id"] = run.dossier["dossier_id"]
        if run.stopped:
            run.review_packet = self._review_packet(run)
        if review_queue is not None and run.stopped:
            self._enqueue_review(run, review_queue)
        if run.external_actions_performed:
            raise RuntimeError("Phase invariant failed: an external action was recorded.")

    # ---- helpers ---------------------------------------------------------------
    def _preflight(self, stage, job: Job) -> Optional[dict]:
        category = AGENT_CATEGORY.get(stage.agent or "", stage.agent or "")
        decision = self.policy.classify(category)
        if stage.permission == "PROHIBITED" or job.permission_class == "PROHIBITED" or decision.prohibited:
            return {
                "code": "prohibited_action",
                "message": f"Stage '{stage.id}' is PROHIBITED and was not executed.",
                "retryable": False,
            }
        if (
            stage.agent in NON_EXECUTABLE_AGENTS
            or category in CONSEQUENTIAL_ACTION_CATEGORIES
            or stage.permission == "APPROVAL_REQUIRED"
            or decision.requires_approval
        ):
            return {
                "code": "phase_blocked",
                "message": (
                    f"Stage '{stage.id}' would be consequential or approval-gated. "
                    "Phase 2 did not execute it."
                ),
                "retryable": False,
            }
        if stage.agent not in self.runtimes:
            return {
                "code": "unknown_agent_runtime",
                "message": f"No offline runtime is registered for '{stage.agent}'.",
                "retryable": False,
            }
        return None

    def _collect_inputs(self, run: OpportunityRun, stage) -> dict:
        return {
            "objective": run.objective,
            "fixture": run.fixture if stage.agent in FIXTURE_AGENTS else None,
            "upstream": {stage_id: output for stage_id, output in run.outputs.items()},
        }

    def _retryable(self, job: Job, errors: List[dict]) -> bool:
        if not errors or job.attempts >= job.retry_policy.max_attempts:
            return False
        retryable = set(job.retry_policy.retryable_error_codes)
        terminal = set(job.retry_policy.terminal_error_codes)
        for error in errors:
            code = error.get("code", "")
            if code in terminal or not error.get("retryable") or code not in retryable:
                return False
        return True

    def _mirror_output(self, run: OpportunityRun, output: dict) -> None:
        for item in iter_claims(output):
            field_name = item.get("field") or "claim"
            claim_id = item.get("claim_id") or "item"
            key = f"{field_name}:{claim_id}"
            status = item.get("epistemic_status")
            if status == "FACT" and item.get("support_scope") == "mock":
                sources = []
                for evidence_id in item.get("evidence_ids") or []:
                    record = run.evidence.get(evidence_id)
                    if record is not None:
                        sources.append(record.source_reference)
                if sources:
                    run.project.record_evidence(
                        key,
                        value={
                            "statement": item.get("statement"),
                            "epistemic_status": "FACT",
                            "support_scope": "mock",
                        },
                        sources=sources,
                        verified=True,
                    )
                    continue
            if status == "UNKNOWN" or status is None:
                run.project.record_evidence(key)
                continue
            run.project.record_evidence(
                key,
                value={"statement": item.get("statement"), "epistemic_status": status},
                verified=False,
            )
        for name in output.get("unknown_inputs") or []:
            run.project.record_evidence(f"economics:{name}")
        if output.get("break_even_units") == "UNKNOWN":
            run.project.record_evidence("economics:break_even_units")

    def _mark_skipped(self, run: OpportunityRun, stage, notes: str) -> None:
        if run.stage_status(stage.id) == "pending":
            run.project.update_stage(stage.id, "skipped", notes=notes)
        job = run.jobs.get(stage.id)
        if job is not None and job.status == "pending":
            job.status = "blocked"
            job.validate()

    def _stop(self, run: OpportunityRun, reason: str, **details: Any) -> None:
        if run.stopped:
            return
        run.stopped = True
        run.stop_reason = reason
        run.stop_details = details
        run.project.set_status(_STOP_STATUS.get(reason, "on_hold"))
        run.audit.record(
            "workflow_stopped",
            project_id=run.project.project_id,
            workflow_id=run.workflow.id,
            reason=reason,
            **_jsonable(details),
        )

    def _decide(self, run: OpportunityRun, actor: str, summary: str, rationale: Optional[str] = None) -> None:
        run.project.add_decision(actor, summary, rationale=rationale)
        run.audit.record(
            "decision_recorded",
            project_id=run.project.project_id,
            actor=actor,
            summary=summary,
        )

    def _approval_block_reason(self, run: OpportunityRun) -> Optional[str]:
        compliance = run.outputs.get("compliance_screen") or {}
        ip_spec = run.gate_config["gates"]["unresolved_ip_risk"]
        prohibited_spec = run.gate_config["gates"]["unresolved_prohibited_product_risk"]
        if compliance:
            blocking = set(ip_spec["blocking_statuses"])
            for field in ip_spec["fields"]:
                if compliance.get(field, "UNKNOWN") in blocking:
                    return "unresolved_ip_risk"
            if compliance.get(prohibited_spec["field"], "UNKNOWN") in set(prohibited_spec["blocking_statuses"]):
                return "unresolved_prohibited_product_risk"
            return None
        if any(stage.id == "compliance_screen" for stage in run.workflow.stages):
            if run.stage_status("compliance_screen") != "passed":
                return "compliance_screening_incomplete"
        return None

    def _review_packet(self, run: OpportunityRun) -> dict:
        dossier = run.dossier or {}
        sections = dossier.get("sections") or {}
        packet_type = {
            "human_review": "human_review",
            "escalate": "escalation_review",
        }.get(run.stop_reason or "", "stop_report")
        return {
            "packet_type": packet_type,
            "project_id": run.project.project_id,
            "workflow_id": run.workflow.id,
            "objective": run.objective,
            "phase": PHASE,
            "dossier_id": dossier.get("dossier_id"),
            "stop_reason": run.stop_reason,
            "approval": {
                "action": run.pending_approval_action,
                "status": "pending" if packet_type == "human_review" else "not_requested",
                "approver": "human_owner",
            },
            "unknowns": (sections.get("unknowns") or {}).get("content", []),
            "risks": (sections.get("risks") or {}).get("content", []),
            "failed_validation_criteria": (sections.get("failed_validation_criteria") or {}).get("content", []),
            "consequential_actions_performed": [],
            "statement": (
                "Workflow stopped. No store creation, supplier commitment, purchase, "
                "publication, advertising, customer communication, Fiverr order, or refund was performed."
            ),
        }

    def apply_review_decision(
        self,
        run: OpportunityRun,
        review_queue: Any,
        review_id: str,
        decision: str,
        note: str = "",
        decided_by: str = "human_owner",
    ) -> dict:
        """Record a human review decision. The decision never executes an external action."""
        item = review_queue.decide(review_id, decision, note=note, decided_by=decided_by)
        recorded = item["decision"]
        run.audit.record(
            "review_decision",
            project_id=run.project.project_id,
            review_id=review_id,
            decision=recorded["decision"],
            blocked_reason=recorded.get("blocked_reason"),
            executed_external_action=False,
        )
        return item

    def _audit_evidence(self, run: OpportunityRun, record) -> None:
        run.audit.record(
            "evidence_added",
            project_id=run.project.project_id,
            evidence_id=record.evidence_id,
            source_type=record.source_type,
            verification_status=record.verification_status,
            collected_by=record.collected_by,
        )

    def _ingest_output_evidence(self, run: OpportunityRun, output: Any) -> None:
        if not isinstance(output, dict):
            return
        for raw in output.get("evidence_records") or []:
            if not isinstance(raw, dict):
                raise EvidenceError("Connector evidence record must be an object.")
            record = record_from_dict(raw)
            existing = run.evidence.get(record.evidence_id)
            if existing is not None:
                if existing.to_dict() != record.to_dict():
                    raise EvidenceError(f"Conflicting evidence id {record.evidence_id}.")
                continue
            run.evidence.add(record)
            self._audit_evidence(run, record)

    def _enqueue_review(self, run: OpportunityRun, review_queue: Any) -> None:
        from ..review.queue import build_review_item

        item = build_review_item(run, approval_block_reason=self._approval_block_reason(run))
        stored = review_queue.enqueue(item)
        run.review_item_id = stored["review_id"]
        if run.review_packet is not None:
            run.review_packet["review_id"] = stored["review_id"]
        run.audit.record(
            "review_enqueued",
            project_id=run.project.project_id,
            review_id=stored["review_id"],
            workflow_id=run.workflow.id,
            status=stored["status"],
            stop_reason=run.stop_reason,
        )


def _jsonable(details: dict) -> dict:
    cleaned = {}
    for key, value in details.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
        else:
            cleaned[key] = value
    return cleaned


def build_runner() -> WorkflowRunner:
    from ..agents.registry import AgentRegistry
    from ..policy.approval import load_default_policy
    from ..workflows.loader import load_all_workflows

    return WorkflowRunner(AgentRegistry.load(), load_default_policy(), load_all_workflows())
