"""Market Research agent.

Organizes the supplied TEST/MOCK packet and the trend handoff. Epistemic
labels are copied. They are not upgraded.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ...protocol.knowledge import claim, iter_claims
from ...protocol.models import Job, make_result
from .common import confidence_for, fixture_of, passthrough_claim, stage_output

ECONOMICS_KEYS = (
    "currency",
    "selling_price",
    "product_cost",
    "shipping",
    "platform_fees",
    "payment_fees",
    "fulfillment_cost",
    "fixed_costs",
)


class MarketResearchAgent:
    agent_id = "market_research_agent"

    def run(self, job: Job, run) -> object:
        fixture = fixture_of(job)
        trend = stage_output(job, "trend_discovery")
        market = fixture.get("market") or {}
        output = organize_market(fixture, market, trend)
        unknowns = [item["statement"] if isinstance(item, dict) else str(item) for item in output["unknowns"]]
        fact_count = sum(1 for item in iter_claims(output) if item.get("epistemic_status") == "FACT")
        level = "medium" if fact_count else "low"
        return make_result(
            job,
            findings=list(output["demand_signals"]),
            structured_output=output,
            evidence=_evidence_ids(output),
            assumptions=list(output["assumptions"]),
            unknowns=unknowns,
            confidence=confidence_for(level, "Labels were copied from supplied TEST/MOCK inputs and not upgraded."),
            recommended_next_action="proceed",
        )


def organize_market(fixture: Dict[str, Any], market: Dict[str, Any], trend: Dict[str, Any]) -> Dict[str, Any]:
    candidates = list(trend.get("candidate_opportunities") or [])
    if candidates:
        first = candidates[0]
        niche = claim(
            claim_id="niche-from-trend",
            field="product_niche_hypothesis",
            statement=first.get("statement") or first.get("theme") or "UNKNOWN",
            epistemic_status=first.get("epistemic_status") or "UNKNOWN",
            evidence_ids=list(first.get("evidence_ids") or []),
            notes="Passed through from trend discovery. Not upgraded.",
        )
    else:
        niche = claim(
            claim_id="niche-missing",
            field="product_niche_hypothesis",
            statement=fixture.get("niche_hypothesis") or "No niche hypothesis was supplied.",
            epistemic_status="UNKNOWN",
            notes="No trend handoff was available. The fixture text was not upgraded to FACT.",
        )

    economics = fixture.get("economics") or {}
    economics_inputs = {key: economics.get(key, None) for key in ECONOMICS_KEYS}
    assumptions = [
        claim(
            claim_id=f"assumption-{index}",
            field="assumption",
            statement=text,
            epistemic_status="ASSUMPTION",
            notes="Explicit assumption from the TEST/MOCK packet.",
        )
        for index, text in enumerate(fixture.get("assumptions") or [])
    ]
    for risk in market.get("market_risks") or []:
        if isinstance(risk, dict) and risk.get("epistemic_status") == "ASSUMPTION":
            assumptions.append(passthrough_claim(risk, "market_risk"))

    customer = passthrough_claim(market.get("target_customer"), "target_customer")
    competition = passthrough_claim(market.get("competition"), "competition")
    pricing = passthrough_claim(market.get("pricing_context"), "pricing_context")
    seasonality = passthrough_claim(market.get("seasonality"), "seasonality")
    signals = [passthrough_claim(item, "demand") for item in (market.get("demand_signals") or [])]
    risks = [passthrough_claim(item, "market_risk") for item in (market.get("market_risks") or [])]

    organized = {
        "market_summary": niche,
        "niche_hypothesis": niche,
        "business_model": fixture.get("business_model") or "UNKNOWN",
        "demand_present": market.get("demand_present", None),
        "demand_present_epistemic_status": market.get("demand_present_epistemic_status", "UNKNOWN"),
        "demand_present_evidence_ids": list(market.get("demand_present_evidence_ids") or []),
        "demand_signals": signals,
        "customer_hypothesis": customer,
        "competitive_context": competition,
        "pricing_context": pricing,
        "seasonality": seasonality,
        "market_risks": risks,
        "economics_inputs": economics_inputs,
        "compliance_inputs": dict(fixture.get("compliance") or {}),
        "supplier_inputs": dict(fixture.get("supplier") or {}),
        "assumptions": assumptions,
        "unknowns": [],
    }
    organized["unknowns"] = _unknown_claims(organized)
    return organized


def _unknown_claims(organized: Dict[str, Any]) -> List[dict]:
    unknowns = []
    for item in iter_claims(organized):
        if item.get("epistemic_status") == "UNKNOWN":
            unknowns.append(item)
    if organized.get("demand_present_epistemic_status") == "UNKNOWN":
        unknowns.append(
            claim(
                claim_id="demand-present-unknown",
                field="demand",
                statement="Whether demand is present was not supplied.",
                epistemic_status="UNKNOWN",
            )
        )
    return unknowns


def _evidence_ids(output: Dict[str, Any]) -> List[str]:
    found: List[str] = []
    for item in iter_claims(output):
        for evidence_id in item.get("evidence_ids") or []:
            if evidence_id not in found:
                found.append(evidence_id)
    found.extend(evidence_id for evidence_id in output.get("demand_present_evidence_ids") or [] if evidence_id not in found)
    return found
