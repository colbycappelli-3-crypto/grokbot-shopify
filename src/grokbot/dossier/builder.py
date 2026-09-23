"""Opportunity dossier.

The dossier aggregates completed work and keeps negative evidence, failed
gates, assumptions, and UNKNOWN fields visible.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from ..clock import utc_now
from ..protocol.knowledge import iter_claims
from ..validation import validate


def _section(title: str, content: Any, epistemic_status: str, negative_items: List[Any] | None = None) -> dict:
    return {
        "title": title,
        "content": content,
        "epistemic_status": epistemic_status,
        "negative_items": list(negative_items or []),
    }


def _not_assessed(reason: str) -> dict:
    return {
        "assessed": False,
        "reason": reason,
        "value": "UNKNOWN",
    }


def build_dossier(run: Any) -> dict:
    fixture = run.fixture or {}
    classification = fixture.get("data_classification", "UNSOURCED")
    banner = fixture.get("banner") or (
        "UNSOURCED — no fixture was supplied. Missing information is UNKNOWN."
    )
    market = run.outputs.get("market_research") or {}
    trend = run.outputs.get("trend_discovery") or {}
    validation = run.outputs.get("product_validation") or {}
    economics = run.outputs.get("unit_economics") or {}
    compliance = run.outputs.get("compliance_screen") or {}
    supplier = run.outputs.get("supplier_evidence") or {}

    assumptions = _assumptions(run, market)
    unknowns = _unknowns(run, market, economics, supplier, compliance)
    failed = _failed_criteria(run, validation)
    risks = _risks(market, compliance, supplier)
    decisions = _decisions(run)

    if economics:
        economics_section = _section(
            "Unit economics",
            {"assessed": True, **economics},
            "UNKNOWN" if economics.get("gross_profit") == "UNKNOWN" else "MIXED",
            negative_items=[
                f"{name} is UNKNOWN. No value was invented."
                for name in (economics.get("unknown_inputs") or [])
            ]
            + (
                ["Break-even units are UNKNOWN."]
                if economics.get("break_even_units") == "UNKNOWN"
                else []
            ),
        )
    else:
        economics_section = _section(
            "Unit economics",
            _not_assessed("Unit economics stage did not run."),
            "UNKNOWN",
            negative_items=["Unit economics stage did not run."],
        )

    if supplier:
        supplier_negative = []
        if supplier.get("us_fulfillment_evidence_status") != "verified":
            supplier_negative.append(supplier.get("statement") or "US fulfillment evidence is not verified.")
        if supplier.get("commitment_made") is False:
            supplier_negative.append("No supplier commitment was made.")
        supplier_section = _section(
            "Supplier and fulfillment status",
            supplier,
            supplier.get("epistemic_status", "UNKNOWN"),
            negative_items=supplier_negative,
        )
    else:
        supplier_section = _section(
            "Supplier and fulfillment status",
            _not_assessed(
                "No supplier research stage ran. No supplier was contacted. Fulfillment evidence is UNKNOWN."
            ),
            "UNKNOWN",
            negative_items=["No supplier was contacted. Fulfillment evidence is UNKNOWN."],
        )

    compliance_negative = []
    if compliance:
        compliance_negative.extend(compliance.get("blocking_fields") or [])
        for finding in compliance.get("risk_findings") or []:
            if finding.get("status") not in {None, "clear"}:
                compliance_negative.append(finding)
        if compliance.get("blocks_automatic_approval"):
            compliance_negative.append("Automatic approval is blocked by screening.")
        compliance_status = "MIXED" if compliance_negative else "INFERENCE"
    else:
        compliance_negative.append("Compliance/IP screening did not run. Risk is UNKNOWN, not clear.")
        compliance_status = "UNKNOWN"

    demand_claims = list(market.get("demand_signals") or [])
    demand_negative = [
        claim for claim in demand_claims if claim.get("epistemic_status") in {"UNKNOWN", "ASSUMPTION"}
    ]
    if market.get("demand_present") is False:
        demand_negative.append("Supplied evidence states that demand is absent.")

    dossier = {
        "dossier_id": f"dos-{uuid.uuid4().hex[:12]}",
        "project_id": run.project.project_id,
        "workflow_id": run.workflow.id,
        "data_classification": classification if classification in {"TEST_MOCK", "UNSOURCED"} else "UNSOURCED",
        "banner": banner,
        "generated_at": utc_now(),
        "sections": {
            "opportunity_identity": _section(
                "Opportunity identity",
                {
                    "project_id": run.project.project_id,
                    "workflow_id": run.workflow.id,
                    "division": run.workflow.division,
                    "objective": run.objective,
                    "fixture_id": fixture.get("fixture_id"),
                    "banner": banner,
                    "phase": run.phase,
                },
                "MIXED",
            ),
            "business_model": _section(
                "Business model",
                {
                    "statement": market.get("business_model") or fixture.get("business_model") or "UNKNOWN",
                    "epistemic_status": "INFERENCE" if fixture.get("business_model") else "UNKNOWN",
                    "notes": "Workflow division selected for this offline run. Not a verified market fact.",
                },
                "INFERENCE" if fixture.get("business_model") else "UNKNOWN",
            ),
            "product_niche_hypothesis": _section(
                "Product or niche hypothesis",
                {
                    "hypothesis": market.get("niche_hypothesis")
                    or {
                        "statement": "No niche hypothesis was produced.",
                        "epistemic_status": "UNKNOWN",
                        "evidence_ids": [],
                    },
                    "declares_opportunity_successful": bool(trend.get("declares_opportunity_successful")),
                },
                (market.get("niche_hypothesis") or {}).get("epistemic_status", "UNKNOWN"),
                negative_items=(
                    ["Trend discovery declared an opportunity successful. That declaration is not accepted."]
                    if trend.get("declares_opportunity_successful")
                    else []
                ),
            ),
            "demand_evidence": _section(
                "Demand evidence",
                {
                    "demand_present": market.get("demand_present", "UNKNOWN"),
                    "demand_present_epistemic_status": market.get("demand_present_epistemic_status", "UNKNOWN"),
                    "signals": demand_claims,
                    "verified_demand_signals": validation.get("verified_demand_signals"),
                },
                _rollup([market.get("demand_present_epistemic_status")] + [c.get("epistemic_status") for c in demand_claims]),
                negative_items=demand_negative,
            ),
            "customer_hypothesis": _section(
                "Customer hypothesis",
                market.get("customer_hypothesis")
                or {"statement": "UNKNOWN", "epistemic_status": "UNKNOWN", "evidence_ids": []},
                (market.get("customer_hypothesis") or {}).get("epistemic_status", "UNKNOWN"),
            ),
            "competitive_context": _section(
                "Competitive context",
                market.get("competitive_context")
                or {"statement": "UNKNOWN", "epistemic_status": "UNKNOWN", "evidence_ids": []},
                (market.get("competitive_context") or {}).get("epistemic_status", "UNKNOWN"),
            ),
            "pricing_context": _section(
                "Pricing context",
                market.get("pricing_context")
                or {"statement": "UNKNOWN", "epistemic_status": "UNKNOWN", "evidence_ids": []},
                (market.get("pricing_context") or {}).get("epistemic_status", "UNKNOWN"),
            ),
            "unit_economics": economics_section,
            "supplier_fulfillment_status": supplier_section,
            "compliance_ip_screening": _section(
                "Compliance and IP screening",
                compliance
                or {
                    "recommendation": "UNKNOWN",
                    "legal_advice": False,
                    "disclaimer": "Screening did not run. This is not a clearance and not legal advice.",
                },
                compliance_status,
                negative_items=compliance_negative,
            ),
            "assumptions": _section(
                "Assumptions",
                assumptions,
                "ASSUMPTION" if assumptions else "UNKNOWN",
                negative_items=assumptions,
            ),
            "unknowns": _section(
                "Unknowns",
                unknowns,
                "UNKNOWN",
                negative_items=unknowns,
            ),
            "failed_validation_criteria": _section(
                "Failed validation criteria",
                failed,
                "NOT_APPLICABLE" if not failed else "MIXED",
                negative_items=failed,
            ),
            "risks": _section(
                "Risks",
                risks,
                "MIXED" if risks else "UNKNOWN",
                negative_items=risks,
            ),
            "evidence_index": _section(
                "Evidence index",
                run.evidence.to_list(),
                "MIXED" if len(run.evidence) else "UNKNOWN",
                negative_items=[
                    record
                    for record in run.evidence.to_list()
                    if record["verification_status"] != "verified"
                ],
            ),
            "agent_decisions": _section(
                "Agent decisions",
                decisions,
                "MIXED" if decisions else "UNKNOWN",
                negative_items=[
                    item
                    for item in decisions
                    if item["status"] != "completed"
                    or item["recommended_next_action"] in {"research_further", "reject", "stop_unresolved_risk"}
                    or item["validation_flags"]
                ],
            ),
            "overall_workflow_status": _section(
                "Overall workflow status",
                {
                    "project_status": run.project.status,
                    "stop_reason": run.stop_reason,
                    "external_actions_performed": list(run.external_actions_performed),
                    "phase": run.phase,
                },
                "FACT",
            ),
            "next_recommended_stage": _section(
                "Next recommended stage",
                {"stage": _next_stage(run)},
                "INFERENCE",
            ),
        },
    }
    validate(dossier, "opportunity_dossier", source=f"dossier:{run.project.project_id}")
    return dossier


def _rollup(statuses: List[Any]) -> str:
    present = [status for status in statuses if status]
    if not present:
        return "UNKNOWN"
    unique = set(present)
    if unique == {"UNKNOWN"}:
        return "UNKNOWN"
    if len(unique) == 1 and "UNKNOWN" not in unique:
        return present[0] if present[0] in {"FACT", "INFERENCE", "ASSUMPTION", "UNKNOWN"} else "MIXED"
    return "MIXED"


def _assumptions(run: Any, market: dict) -> List[Any]:
    items: List[Any] = []
    for result in run.results.values():
        items.extend(result.assumptions)
    items.extend(market.get("assumptions") or [])
    return items


def _unknowns(run: Any, market: dict, economics: dict, supplier: dict, compliance: dict) -> List[Any]:
    items: List[Any] = []
    for result in run.results.values():
        for item in result.unknowns:
            items.append({"agent_id": result.agent_id, "unknown": item})
    for claim in iter_claims(market):
        if claim.get("epistemic_status") == "UNKNOWN":
            items.append(claim)
    for name in economics.get("unknown_inputs") or []:
        items.append({"field": name, "epistemic_status": "UNKNOWN", "statement": f"{name} is UNKNOWN."})
    if economics.get("break_even_units") == "UNKNOWN":
        items.append(
            {
                "field": "break_even_units",
                "epistemic_status": "UNKNOWN",
                "statement": economics.get("break_even_notes") or "Break-even units are UNKNOWN.",
            }
        )
    if supplier.get("epistemic_status") == "UNKNOWN":
        items.append(
            {
                "field": "us_fulfillment",
                "epistemic_status": "UNKNOWN",
                "statement": supplier.get("statement") or "US fulfillment is UNKNOWN.",
            }
        )
    if not compliance:
        items.append(
            {
                "field": "compliance_ip_screening",
                "epistemic_status": "UNKNOWN",
                "statement": "Compliance/IP screening did not run.",
            }
        )
    return items


def _failed_criteria(run: Any, validation: dict) -> List[dict]:
    failed: List[dict] = []
    for item in validation.get("failed_criteria") or []:
        failed.append(item)
    for evaluation in run.gate_results:
        if evaluation.get("passed"):
            continue
        for reason in evaluation.get("reasons") or []:
            if reason.get("severity") == "fail":
                failed.append(
                    {
                        "code": reason.get("code"),
                        "message": reason.get("message"),
                        "gate_id": evaluation.get("gate_id"),
                        "field": reason.get("field"),
                        "observed": reason.get("observed"),
                    }
                )
    return failed


def _risks(market: dict, compliance: dict, supplier: dict) -> List[Any]:
    risks: List[Any] = []
    risks.extend(market.get("market_risks") or [])
    for finding in compliance.get("risk_findings") or []:
        risks.append(finding)
    for name in compliance.get("blocking_fields") or []:
        risks.append(
            {
                "field": name,
                "observed": compliance.get(name),
                "statement": f"{name} is {compliance.get(name)}. Automatic approval is blocked.",
            }
        )
    if supplier.get("us_fulfillment_evidence_status") not in {None, "verified"} and supplier:
        risks.append(
            {
                "field": "us_fulfillment",
                "observed": supplier.get("us_fulfillment_evidence_status"),
                "statement": supplier.get("statement"),
            }
        )
    return risks


def _decisions(run: Any) -> List[dict]:
    decisions = []
    for stage_id, result in run.results.items():
        outcome = None
        if isinstance(result.structured_output, dict):
            outcome = result.structured_output.get("validation_outcome") or result.structured_output.get(
                "recommendation"
            )
        decisions.append(
            {
                "stage_id": stage_id,
                "agent_id": result.agent_id,
                "status": result.status,
                "recommended_next_action": result.recommended_next_action,
                "validation_flags": list(result.validation_flags),
                "errors": list(result.errors),
                "outcome": outcome,
            }
        )
    return decisions


def _next_stage(run: Any) -> str:
    reason = run.stop_reason
    if reason in {"human_review", "awaiting_human_review"} or run.project.status == "awaiting_approval":
        return "human_review"
    if reason == "request_more_research":
        return "additional_research"
    if reason == "reject":
        return "do_not_proceed"
    if reason == "escalate":
        return "human_owner_escalation"
    if reason == "halt":
        return "stopped_pending_review"
    if reason == "terminal_failure":
        return "stopped_on_failure"
    if reason == "phase_blocked":
        return "blocked_consequential_action"
    return "none"
