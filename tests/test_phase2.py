"""Phase 2 offline orchestration, protocol, gates, and workflow simulations."""
import pytest

from grokbot.agents.registry import AgentRegistry
from grokbot.audit.log import AuditLog
from grokbot.cli import main
from grokbot.evidence.ledger import EvidenceLedger, EvidenceRecord
from grokbot.fixtures.loader import load_all_fixtures, load_fixture
from grokbot.gates.evaluator import evaluate_gate
from grokbot.gates.loader import load_validation_gates
from grokbot.gates.rules import (
    assess_supplier,
    compute_unit_economics,
    decide_product_validation,
    screen_compliance,
)
from grokbot.orchestrator.engine import WorkflowRunner, build_runner
from grokbot.policy.approval import ActionClass
from grokbot.protocol.knowledge import enforce_structured_output
from grokbot.protocol.models import RetryPolicy, make_result
from grokbot.validation import SpecValidationError, validate
from grokbot.workflows.loader import WorkflowSpec


def _runner(**kwargs):
    base = build_runner()
    if kwargs.get("runtimes"):
        base.runtimes.update(kwargs["runtimes"])
    if kwargs.get("gate_config"):
        base.gate_config = kwargs["gate_config"]
    return base


def _run(fixture_name, **kwargs):
    fixture = load_fixture(fixture_name)
    runner = _runner(**kwargs)
    run = runner.open_opportunity(fixture["objective"], workflow_id=fixture["workflow_id"], fixture=fixture)
    runner.run(run, faults=kwargs.get("faults"))
    return runner, run


def test_new_agents_are_registered_and_active():
    registry = AgentRegistry.load()
    for agent_id in (
        "trend_discovery_agent",
        "market_research_agent",
        "product_validation_agent",
        "unit_economics_agent",
        "compliance_ip_screening_agent",
        "supplier_research_agent",
        "opportunity_dossier_agent",
    ):
        spec = registry.get(agent_id)
        assert spec.status == "active"
    assert registry.get("product_validation_agent").division == "shared"
    assert "shopify_store_builder_agent" in registry


def test_job_schema_and_creation_fields():
    fixture = load_fixture("promising_pod")
    runner = build_runner()
    run = runner.open_opportunity(fixture["objective"], workflow_id=fixture["workflow_id"], fixture=fixture)
    job = run.jobs["trend_discovery"]
    payload = job.to_dict()
    validate(payload, "job")
    for field in (
        "job_id",
        "project_id",
        "workflow_id",
        "agent_id",
        "objective",
        "required_inputs",
        "supplied_inputs",
        "dependencies",
        "status",
        "permission_class",
        "created_at",
        "evidence_requirements",
        "expected_output_schema",
        "retry_policy",
    ):
        assert field in payload
    assert job.status == "pending"
    assert job.agent_id == "trend_discovery_agent"
    assert job.retry_policy.max_attempts >= 1
    broken = dict(payload)
    del broken["job_id"]
    with pytest.raises(SpecValidationError):
        validate(broken, "job")


def test_agent_result_schema_requires_epistemic_handoff_fields():
    fixture = load_fixture("promising_pod")
    runner = build_runner()
    opened = runner.open_opportunity(fixture["objective"], workflow_id=fixture["workflow_id"], fixture=fixture)
    result = make_result(opened.jobs["trend_discovery"], structured_output={"ok": True})
    validate(result.to_dict(), "agent_result")
    incomplete = result.to_dict()
    del incomplete["unknowns"]
    with pytest.raises(SpecValidationError):
        validate(incomplete, "agent_result")


def test_unsupported_fact_is_downgraded_to_unknown():
    enforced, flags = enforce_structured_output(
        {
            "statement": "Invented sales figure",
            "epistemic_status": "FACT",
            "evidence_ids": [],
            "field": "demand",
        },
        {},
    )
    assert enforced["epistemic_status"] == "UNKNOWN"
    assert "unsupported_fact_downgraded" in flags


def test_runtime_cannot_smuggle_an_unsupported_fact_downstream():
    from grokbot.protocol.models import make_result as build_result

    class BadTrend:
        agent_id = "trend_discovery_agent"

        def run(self, job, run):
            return build_result(
                job,
                structured_output={
                    "candidate_opportunities": [
                        {
                            "candidate_id": "invented",
                            "statement": "Invented fact with no evidence",
                            "epistemic_status": "FACT",
                            "evidence_ids": [],
                            "field": "candidate_opportunity",
                        }
                    ],
                    "declares_opportunity_successful": False,
                    "unknowns": [],
                    "recommended_research": [],
                    "evidence_requirements": [],
                },
            )

    _, run = _run("promising_pod", runtimes={"trend_discovery_agent": BadTrend()})
    candidate = run.outputs["trend_discovery"]["candidate_opportunities"][0]
    assert candidate["epistemic_status"] == "UNKNOWN"
    assert "unsupported_fact_downgraded" in run.results["trend_discovery"].validation_flags
    assert run.outputs["market_research"]["niche_hypothesis"]["epistemic_status"] == "UNKNOWN"


def test_missing_economics_inputs_stay_unknown():
    config = load_validation_gates()
    required = config["gates"]["economics_completeness"]["required_inputs"]
    result = compute_unit_economics({"selling_price": 32, "currency": "USD"}, required)
    assert result["product_cost"] == "UNKNOWN"
    assert result["gross_profit"] == "UNKNOWN"
    assert result["gross_margin"] == "UNKNOWN"
    assert result["break_even_units"] == "UNKNOWN"
    assert result["inputs_invented"] is False


def test_evidence_must_be_marked_mock_and_cannot_use_live_urls():
    ledger = EvidenceLedger()
    with pytest.raises(Exception):
        ledger.add(
            EvidenceRecord(
                evidence_id="ev-bad",
                source_type="mock",
                source_reference="https://example.invalid/real-looking",
                claim_supported="TEST claim",
                collected_by="fixture_loader",
                verification_status="verified",
                notes="TEST/MOCK DATA",
            )
        )
    with pytest.raises(Exception):
        ledger.add(
            EvidenceRecord(
                evidence_id="ev-unmarked",
                source_type="mock",
                source_reference="fixture/plain",
                claim_supported="a claim",
                collected_by="fixture_loader",
                verification_status="verified",
                notes="not marked",
            )
        )


def test_audit_redacts_secret_like_values():
    log = AuditLog()
    event = log.record(
        "decision_recorded",
        api_key="super-secret-value",
        note="ordinary note sk_live_should_not_survive",
    )
    assert event["details"]["api_key"] == "[REDACTED]"
    assert event["details"]["note"] == "[REDACTED]"


def test_fixtures_are_explicitly_mock():
    fixtures = load_all_fixtures()
    ids = {item["fixture_id"] for item in fixtures}
    assert {
        "promising_pod",
        "research_further",
        "rejected_opportunity",
        "attractive_economics_ip_risk",
        "dropship_missing_us_fulfillment",
        "promising_dropship",
    } <= ids
    for fixture in fixtures:
        assert fixture["data_classification"] == "TEST_MOCK"
        assert "MOCK" in fixture["banner"] or "TEST" in fixture["banner"]


def test_margin_threshold_is_configurable_and_not_applied_when_unknown():
    config = load_validation_gates()
    unknown = evaluate_gate("margin_threshold", {"gross_margin": None}, config)
    assert unknown["passed"] is True
    assert unknown["applicable"] is False
    assert unknown["reasons"][0]["code"] == "margin_threshold_not_applicable"

    config["gates"]["margin_threshold"]["min_gross_margin"] = 0.9
    failed = evaluate_gate("margin_threshold", {"gross_margin": 0.45}, config)
    assert failed["passed"] is False
    assert failed["reasons"][0]["code"] == "margin_below_configured_threshold"
    assert failed["reasons"][0]["threshold"] == 0.9


def test_dependency_enforcement_and_structured_handoff():
    _, run = _run("research_further")
    assert run.jobs["trend_discovery"].status == "completed"
    assert run.jobs["market_research"].status == "completed"
    assert run.jobs["product_validation"].status == "completed"
    assert run.jobs["unit_economics"].status == "blocked"
    assert run.jobs["unit_economics"].attempts == 0
    assert run.stage_status("unit_economics") == "skipped"
    market_job = run.jobs["market_research"]
    assert "candidate_opportunities" in market_job.supplied_inputs["upstream"]["trend_discovery"]
    validation_job = run.jobs["product_validation"]
    assert validation_job.supplied_inputs["fixture"] is None
    assert "demand_signals" in validation_job.supplied_inputs["upstream"]["market_research"]
    assigned = [event["details"]["stage_id"] for event in run.audit.of_type("job_assigned")]
    assert assigned.index("trend_discovery") < assigned.index("market_research")
    assert assigned.index("market_research") < assigned.index("product_validation")
    assert "unit_economics" not in assigned


def test_promising_pod_stops_at_human_review_with_dossier():
    runner, run = _run("promising_pod")
    assert run.stop_reason == "human_review"
    assert run.project.status == "awaiting_approval"
    assert run.stage_status("human_review") == "awaiting_approval"
    assert run.stage_status("compile_dossier") == "passed"
    assert run.outputs["trend_discovery"]["declares_opportunity_successful"] is False
    assert run.outputs["product_validation"]["validation_outcome"] == "VALIDATE"
    economics = run.outputs["unit_economics"]
    assert economics["inputs_invented"] is False
    assert economics["gross_profit"] == pytest.approx(14.3)
    assert economics["gross_margin"] == pytest.approx(14.3 / 32)
    assert economics["break_even_units"] == "UNKNOWN"
    assert run.project.data["evidence"]["economics:break_even_units"]["status"] == "UNKNOWN"
    dossier = run.dossier
    assert dossier["data_classification"] == "TEST_MOCK"
    assert dossier["sections"]["failed_validation_criteria"]["content"] == []
    assert dossier["sections"]["next_recommended_stage"]["content"]["stage"] == "human_review"
    assert dossier["sections"]["unit_economics"]["content"]["assessed"] is True
    assert "MOCK" in dossier["banner"]
    assert run.review_packet["packet_type"] == "human_review"
    assert run.review_packet["consequential_actions_performed"] == []
    assert run.external_actions_performed == []
    assert run.audit.of_type("project_created")
    assert run.audit.of_type("job_created")
    assert run.audit.of_type("job_assigned")
    assert run.audit.of_type("job_completed")
    assert run.audit.of_type("evidence_added")
    assert run.audit.of_type("validation_gate_evaluated")
    assert run.audit.of_type("approval_requested")
    assert run.audit.of_type("workflow_stopped")
    evidence = run.evidence.get("ev-demand-1")
    assert evidence.source_type == "mock"
    assert "MOCK" in evidence.notes or "TEST" in evidence.notes
    decision = runner.record_simulated_approval(run, "approved")
    assert decision["executed_external_action"] is False
    assert decision["decision"] == "approved"
    assert run.project.status == "approved"
    assert run.project.status != "launched"
    blocked = runner.attempt_action(run, "launch_store")
    assert blocked["executed"] is False
    assert blocked["blocked"] is True
    assert any(reason["code"] == "phase_2_offline_no_consequential_actions" for reason in blocked["reasons"])


def test_research_further_keeps_unknowns_visible():
    _, run = _run("research_further")
    assert run.outputs["product_validation"]["validation_outcome"] == "RESEARCH_FURTHER"
    assert run.stop_reason == "request_more_research"
    assert run.project.status == "on_hold"
    codes = {
        reason["code"]
        for gate in run.gate_results
        if not gate["passed"]
        for reason in gate["reasons"]
        if reason["severity"] == "fail"
    }
    assert "demand_evidence_incomplete" in codes or "insufficient_verified_demand_evidence" in codes
    assert "excessive_unknown_critical_fields" in codes
    dossier = run.dossier
    assert dossier["sections"]["unit_economics"]["content"]["assessed"] is False
    assert dossier["sections"]["unit_economics"]["content"]["value"] == "UNKNOWN"
    assert dossier["sections"]["unknowns"]["negative_items"]
    assert dossier["sections"]["next_recommended_stage"]["content"]["stage"] == "additional_research"
    assert run.stage_status("human_review") == "skipped"


def test_rejected_opportunity_stops_without_approval():
    _, run = _run("rejected_opportunity")
    assert run.outputs["product_validation"]["validation_outcome"] == "REJECT"
    assert run.stop_reason == "reject"
    assert run.project.status == "rejected"
    failed = run.dossier["sections"]["failed_validation_criteria"]["content"]
    assert any(item.get("code") == "verified_demand_absent" for item in failed)
    assert run.dossier["sections"]["next_recommended_stage"]["content"]["stage"] == "do_not_proceed"
    assert run.pending_approval_action is None
    assert "demand is absent" in run.dossier["sections"]["demand_evidence"]["content"]["signals"][0]["statement"].lower() or any(
        "absent" in str(item).lower() for item in run.dossier["sections"]["demand_evidence"]["negative_items"]
    )


def test_attractive_economics_do_not_clear_unresolved_ip():
    runner, run = _run("attractive_economics_ip_risk")
    assert run.outputs["unit_economics"]["gross_margin"] > 0.25
    assert run.outputs["compliance_screen"]["blocks_automatic_approval"] is True
    assert run.outputs["compliance_screen"]["legal_advice"] is False
    assert run.stop_reason == "escalate"
    assert run.project.status == "on_hold"
    text = str(run.dossier["sections"]["compliance_ip_screening"]["content"])
    assert "MOCKBRAND-XYZZY" in text or any(
        "MOCKBRAND-XYZZY" in str(item) for item in run.dossier["sections"]["risks"]["content"]
    )
    assert any(
        item.get("code") == "unresolved_ip_risk"
        for item in run.dossier["sections"]["failed_validation_criteria"]["content"]
    )
    decision = runner.record_simulated_approval(run, "approved")
    assert decision["decision"] == "blocked"
    assert decision["blocked_reason"] == "unresolved_ip_risk"
    assert decision["executed_external_action"] is False
    assert run.project.status != "approved"


def test_dropship_missing_us_fulfillment_stays_unknown():
    _, run = _run("dropship_missing_us_fulfillment")
    assert run.outputs["supplier_evidence"]["commitment_made"] is False
    assert run.outputs["supplier_evidence"]["external_contact_made"] is False
    assert run.outputs["supplier_evidence"]["us_fulfillment_available"] == "UNKNOWN"
    assert run.stop_reason == "request_more_research"
    assert run.jobs["unit_economics"].status == "blocked"
    codes = [
        reason["code"]
        for gate in run.gate_results
        if not gate["passed"]
        for reason in gate["reasons"]
        if reason["severity"] == "fail"
    ]
    assert "us_fulfillment_evidence_missing" in codes
    supplier = run.dossier["sections"]["supplier_fulfillment_status"]
    assert supplier["epistemic_status"] == "UNKNOWN"
    assert run.dossier["sections"]["unit_economics"]["content"]["assessed"] is False
    assert "not a real" in run.dossier["banner"].lower() or "TEST/MOCK" in run.dossier["banner"]


def test_promising_dropship_stops_at_human_review_without_supplier_contact():
    _, run = _run("promising_dropship")
    assert run.stop_reason == "human_review"
    assert run.project.status == "awaiting_approval"
    supplier = run.outputs["supplier_evidence"]
    assert supplier["us_fulfillment_evidence_status"] == "verified"
    assert supplier["commitment_made"] is False
    assert supplier["external_contact_made"] is False
    assert supplier["candidate_suppliers"][0]["display_name"] == "MOCK Supplier Alpha"
    assert run.outputs["product_validation"]["validation_outcome"] == "VALIDATE"
    assert run.external_actions_performed == []
    assert run.review_packet["packet_type"] == "human_review"
    assert run.dossier["sections"]["next_recommended_stage"]["content"]["stage"] == "human_review"


def test_retryable_failure_is_retried_and_terminal_failure_stops():
    _, retried = _run(
        "promising_pod",
        faults={
            "trend_discovery": [
                {"code": "transient_agent_error", "message": "temporary test fault", "retryable": True}
            ]
        },
    )
    assert retried.jobs["trend_discovery"].attempts == 2
    assert retried.jobs["trend_discovery"].status == "completed"
    assert retried.stop_reason == "human_review"
    assert retried.audit.of_type("retry_scheduled")
    assert any(event["details"].get("will_retry") is True for event in retried.audit.of_type("job_failed"))

    _, stopped = _run(
        "promising_pod",
        faults={"trend_discovery": [{"code": "terminal_agent_error", "message": "terminal test fault", "retryable": False}]},
    )
    assert stopped.jobs["trend_discovery"].attempts == 1
    assert stopped.jobs["trend_discovery"].status == "failed"
    assert stopped.jobs["market_research"].status == "blocked"
    assert stopped.jobs["market_research"].attempts == 0
    assert stopped.stop_reason == "terminal_failure"
    assert stopped.dossier is not None
    assert not stopped.audit.of_type("retry_scheduled")


def test_prohibited_and_consequential_actions_are_blocked():
    runner = build_runner()
    workflow = WorkflowSpec.from_dict(
        {
            "id": "consequential_block_test",
            "name": "Consequential block test",
            "version": "0.2.0",
            "division": "print_on_demand",
            "description": "Ensures Phase 2 does not execute store building.",
            "stages": [
                {
                    "id": "store_build",
                    "name": "Assemble store",
                    "type": "action",
                    "agent": "shopify_store_builder_agent",
                    "permission": "APPROVAL_REQUIRED",
                    "depends_on": [],
                }
            ],
        }
    )
    runner.workflows[workflow.id] = workflow

    class Boom:
        def run(self, job, run):
            raise AssertionError("consequential runtime must not be called")

    runner.runtimes["shopify_store_builder_agent"] = Boom()
    run = runner.open_opportunity("Do not build a store", workflow_id=workflow.id)
    runner.run(run)
    assert run.stop_reason == "phase_blocked"
    assert run.external_actions_performed == []
    assert run.jobs["store_build"].attempts == 0
    assert run.audit.of_type("action_blocked")

    prohibited = WorkflowSpec.from_dict(
        {
            "id": "prohibited_block_test",
            "name": "Prohibited block test",
            "version": "0.2.0",
            "division": "shared",
            "description": "Ensures a PROHIBITED stage is not executed.",
            "stages": [
                {
                    "id": "bad_stage",
                    "name": "Bad stage",
                    "type": "action",
                    "agent": "market_research_agent",
                    "permission": "PROHIBITED",
                    "depends_on": [],
                }
            ],
        }
    )
    runner.workflows[prohibited.id] = prohibited
    runner.runtimes["market_research_agent"] = Boom()
    blocked_run = runner.open_opportunity("Do not run", workflow_id=prohibited.id)
    runner.run(blocked_run)
    assert blocked_run.jobs["bad_stage"].attempts == 0
    assert blocked_run.results["bad_stage"].errors[0]["code"] == "prohibited_action"
    assert blocked_run.external_actions_performed == []

    sample = runner.open_opportunity("Guard checks", workflow_id="pod_opportunity_discovery", fixture=load_fixture("promising_pod"))
    for category in ("expose_credentials", "purchase", "ip_infringement", "supplier_commitment"):
        decision = runner.attempt_action(sample, category)
        assert decision["executed"] is False
        assert decision["blocked"] is True
    credentials = runner.attempt_action(sample, "expose_credentials")
    assert credentials["action_class"] == ActionClass.PROHIBITED.value


def test_supplier_commitment_flag_is_refused():
    assessed = assess_supplier(
        {
            "commitment_made": True,
            "us_fulfillment_evidence_status": "unknown",
            "epistemic_status": "UNKNOWN",
            "evidence_ids": [],
            "statement": "TEST/MOCK supplier input tried to set a commitment.",
            "candidate_suppliers": [],
        }
    )
    assert assessed["commitment_made"] is False
    assert assessed["external_contact_made"] is False
    assert "supplier_commitment_refused" in assessed["validation_flags"]


def test_compliance_screening_is_not_legal_advice():
    screened = screen_compliance({"trademark_risk": "unresolved", "copyright_risk": "clear"})
    assert screened["legal_advice"] is False
    assert screened["blocks_automatic_approval"] is True
    assert screened["recommendation"] == "escalate"


def test_validate_and_simulate_commands():
    assert main(["validate"]) == 0
    assert main(["simulate", "pod_opportunity_discovery", "--fixture", "promising_pod"]) == 0
    assert main(["simulate", "us_dropshipping_opportunity_discovery", "--fixture", "promising_dropship"]) == 0


def test_explicit_validation_rules_reject_confirmed_prohibited_product():
    config = load_validation_gates()
    decision = decide_product_validation(
        {
            "demand_present": True,
            "demand_present_epistemic_status": "FACT",
            "demand_present_evidence_ids": ["ev-1"],
            "demand_signals": [
                {"epistemic_status": "FACT", "evidence_ids": ["ev-1"], "statement": "TEST signal"}
            ],
            "customer_hypothesis": {"epistemic_status": "INFERENCE", "statement": "buyers"},
            "competitive_context": {"epistemic_status": "INFERENCE", "statement": "context"},
            "pricing_context": {"epistemic_status": "FACT", "evidence_ids": ["ev-2"], "statement": "price"},
            "compliance_inputs": {"prohibited_product_risk": "confirmed"},
        },
        config,
    )
    assert decision["validation_outcome"] == "REJECT"
    assert decision["failed_criteria"][0]["code"] == "prohibited_product_confirmed"


def test_discovery_workflow_is_identified_from_division():
    runner = build_runner()
    assert runner.identify_workflow(division="print_on_demand").id == "pod_opportunity_discovery"
    assert runner.identify_workflow(division="us_dropshipping").id == "us_dropshipping_opportunity_discovery"


def test_phase2_modules_do_not_import_network_clients():
    from pathlib import Path

    banned = ("import requests", "import httpx", "import urllib.request", "import socket")
    urllib_allowed = {"shopify_read.py"}
    root = Path(__file__).resolve().parents[1] / "src" / "grokbot"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for item in banned:
            if item == "import urllib.request" and path.name in urllib_allowed:
                continue
            assert item not in text, f"{path} contains {item}"


def test_retry_policy_object_is_on_the_job():
    policy = RetryPolicy(max_attempts=2)
    assert "transient_agent_error" in policy.retryable_error_codes
    assert "terminal_agent_error" in policy.terminal_error_codes
    restored = RetryPolicy.from_dict(policy.to_dict())
    assert restored.max_attempts == 2
