"""Explicit, configurable commerce-screening rules.

Thresholds come from the validation-gate config. These functions do not invent
missing inputs, and they do not treat UNKNOWN as verified.
"""
from __future__ import annotations

from math import ceil
from typing import Any, Dict, List, Optional


def verified_demand_count(market: Dict[str, Any]) -> int:
    """Count positive FACT demand signals. A verified absence is not positive demand."""
    if market.get("demand_present") is False:
        return 0
    count = 0
    for signal in market.get("demand_signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("epistemic_status") == "FACT" and signal.get("evidence_ids"):
            count += 1
    return count


def _claim_unknown(node: Any) -> bool:
    if not isinstance(node, dict):
        return True
    return node.get("epistemic_status", "UNKNOWN") == "UNKNOWN"


def critical_unknown_fields(market: Dict[str, Any], critical_fields: List[str]) -> List[str]:
    unknown: List[str] = []
    for name in critical_fields:
        if _is_critical_unknown(market, name):
            unknown.append(name)
    return unknown


def _is_critical_unknown(market: Dict[str, Any], field: str) -> bool:
    if field == "demand":
        known_absence = (
            market.get("demand_present") is False
            and market.get("demand_present_epistemic_status") == "FACT"
            and bool(market.get("demand_present_evidence_ids"))
        )
        if known_absence:
            return False
        present_fact = (
            market.get("demand_present") is True
            and market.get("demand_present_epistemic_status") == "FACT"
            and bool(market.get("demand_present_evidence_ids"))
        )
        return not present_fact and verified_demand_count(market) == 0
    key = {
        "target_customer": "customer_hypothesis",
        "competition": "competitive_context",
    }.get(field, field)
    node = market.get(key)
    if node is None and field == "target_customer":
        node = market.get("target_customer")
    if node is None and field == "competition":
        node = market.get("competition")
    return _claim_unknown(node)


def decide_product_validation(market: Dict[str, Any], gate_config: Dict[str, Any]) -> Dict[str, Any]:
    """Return VALIDATE, RESEARCH_FURTHER, or REJECT from explicit rules."""
    gates = gate_config["gates"]
    minimum = gates["minimum_evidence_completeness"]["min_verified_demand_signals"]
    critical_fields = list(gates["excessive_unknown_critical_fields"]["critical_fields"])
    max_unknown = gates["excessive_unknown_critical_fields"]["max_unknown"]

    failed: List[dict] = []
    gaps: List[str] = []
    rules: List[str] = []
    compliance = market.get("compliance_inputs") or {}
    prohibited = compliance.get("prohibited_product_risk", "UNKNOWN")

    if prohibited == "confirmed":
        rules.append("reject_when_prohibited_product_confirmed")
        failed.append(
            {
                "code": "prohibited_product_confirmed",
                "message": "Supplied screening marks prohibited-product risk as confirmed.",
            }
        )
        return _decision("REJECT", "fail", failed, ["prohibited_product_risk"], rules, market, minimum, critical_fields)

    demand_present = market.get("demand_present")
    demand_status = market.get("demand_present_epistemic_status", "UNKNOWN")
    demand_evidence = list(market.get("demand_present_evidence_ids") or [])
    if demand_present is False and demand_status == "FACT" and demand_evidence:
        rules.append("reject_when_verified_demand_absent")
        failed.append(
            {
                "code": "verified_demand_absent",
                "message": "Verified evidence states that demand is absent. Absence is not being treated as unverified.",
            }
        )
        return _decision("REJECT", "fail", failed, ["demand"], rules, market, minimum, critical_fields)

    verified = verified_demand_count(market)
    if verified < minimum:
        rules.append("research_when_demand_evidence_below_minimum")
        failed.append(
            {
                "code": "demand_evidence_incomplete",
                "message": (
                    f"Verified demand signals ({verified}) are below the configured "
                    f"minimum ({minimum})."
                ),
            }
        )
        gaps.append("demand")

    unknown_fields = critical_unknown_fields(market, critical_fields)
    if len(unknown_fields) > max_unknown:
        rules.append("research_when_critical_fields_unknown")
        failed.append(
            {
                "code": "excessive_unknown_critical_fields",
                "message": (
                    "UNKNOWN critical fields: "
                    + ", ".join(unknown_fields)
                    + f". Configured max_unknown is {max_unknown}."
                ),
            }
        )
        gaps.extend(field for field in unknown_fields if field not in gaps)

    if failed:
        return _decision(
            "RESEARCH_FURTHER",
            "insufficient_evidence",
            failed,
            gaps,
            rules,
            market,
            minimum,
            critical_fields,
        )

    rules.append("validate_when_minimum_evidence_present_and_no_rejection")
    return _decision("VALIDATE", "pass", [], [], rules, market, minimum, critical_fields)


def _decision(
    outcome: str,
    verdict: str,
    failed: List[dict],
    gaps: List[str],
    rules: List[str],
    market: Dict[str, Any],
    minimum: int,
    critical_fields: List[str],
) -> Dict[str, Any]:
    rationale = {
        "VALIDATE": "Configured evidence minimum is met and no rejection rule fired.",
        "RESEARCH_FURTHER": "Evidence is incomplete or critical fields are UNKNOWN.",
        "REJECT": "An explicit rejection rule fired.",
    }[outcome]
    return {
        "validation_outcome": outcome,
        "validation_verdict": {"outcome": verdict, "rationale": rationale},
        "failed_criteria": failed,
        "evidence_gaps": gaps,
        "rules_applied": rules,
        "unknown_critical_fields": critical_unknown_fields(market, critical_fields),
        "verified_demand_signals": verified_demand_count(market),
        "configured_minimum_demand_signals": minimum,
    }


def compute_unit_economics(inputs: Optional[Dict[str, Any]], required_inputs: List[str]) -> Dict[str, Any]:
    """Compute profit only from supplied numbers. Missing values stay UNKNOWN."""
    inputs = inputs or {}
    values: Dict[str, Any] = {}
    unknowns: List[str] = []
    for key in required_inputs:
        raw = inputs.get(key, None)
        if raw is None or raw == "UNKNOWN":
            values[key] = "UNKNOWN"
            unknowns.append(key)
        else:
            values[key] = raw

    currency = inputs.get("currency")
    result: Dict[str, Any] = {
        "currency": currency if currency else "UNKNOWN",
        "unknown_inputs": unknowns,
        "inputs_invented": False,
        "formula": (
            "gross_profit = selling_price - product_cost - shipping - "
            "platform_fees - payment_fees - fulfillment_cost"
        ),
        "notes": "Missing inputs stay UNKNOWN. No cost was invented to complete a calculation.",
        **values,
    }
    fixed = inputs.get("fixed_costs", None)
    result["fixed_costs"] = "UNKNOWN" if fixed is None or fixed == "UNKNOWN" else fixed

    if unknowns or any(values[key] == "UNKNOWN" for key in required_inputs):
        result["gross_profit"] = "UNKNOWN"
        result["gross_margin"] = "UNKNOWN"
        result["break_even_units"] = "UNKNOWN"
        result["break_even_notes"] = "Break-even was not calculated because required inputs are UNKNOWN."
        return result

    selling = float(values["selling_price"])
    if selling == 0:
        result["gross_profit"] = "UNKNOWN"
        result["gross_margin"] = "UNKNOWN"
        result["break_even_units"] = "UNKNOWN"
        result["break_even_notes"] = "Selling price is zero, so margin and break-even are UNKNOWN."
        return result

    gross_profit = (
        selling
        - float(values["product_cost"])
        - float(values["shipping"])
        - float(values["platform_fees"])
        - float(values["payment_fees"])
        - float(values["fulfillment_cost"])
    )
    result["gross_profit"] = gross_profit
    result["gross_margin"] = gross_profit / selling
    if result["fixed_costs"] == "UNKNOWN":
        result["break_even_units"] = "UNKNOWN"
        result["break_even_notes"] = "Fixed costs were not supplied, so break-even units are UNKNOWN."
    elif gross_profit <= 0:
        result["break_even_units"] = "UNKNOWN"
        result["break_even_notes"] = "Gross profit per unit is not positive, so break-even units are UNKNOWN."
    else:
        result["break_even_units"] = ceil(float(result["fixed_costs"]) / gross_profit)
        result["break_even_notes"] = "break_even_units = ceil(fixed_costs / gross_profit)."
    return result


def screen_compliance(inputs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Screen supplied flags. This does not query a register and is not legal advice."""
    inputs = inputs or {}

    def risk(name: str) -> str:
        value = inputs.get(name, "UNKNOWN")
        if value not in {"clear", "unresolved", "confirmed", "UNKNOWN"}:
            return "UNKNOWN"
        return value

    screened = {
        "trademark_risk": risk("trademark_risk"),
        "copyright_risk": risk("copyright_risk"),
        "prohibited_product_risk": risk("prohibited_product_risk"),
        "deceptive_marketing_risk": risk("deceptive_marketing_risk"),
        "platform_policy_risk": risk("platform_policy_risk"),
    }
    blocking = [
        name
        for name in ("trademark_risk", "copyright_risk", "prohibited_product_risk")
        if screened[name] != "clear"
    ]
    if blocking:
        recommendation = "escalate"
    elif screened["deceptive_marketing_risk"] != "clear" or screened["platform_policy_risk"] != "clear":
        recommendation = "review"
    else:
        recommendation = "clear"
    return {
        "risk_findings": list(inputs.get("findings") or []),
        "recommendation": recommendation,
        **screened,
        "legal_advice": False,
        "disclaimer": (
            "Screening only. This is not professional legal advice and no trademark, "
            "copyright, or product register was queried."
        ),
        "blocks_automatic_approval": recommendation != "clear",
        "blocking_fields": blocking,
    }


def assess_supplier(inputs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Restate supplied fulfillment evidence. Never contacts or commits to a supplier."""
    inputs = inputs or {}
    flags: List[str] = []
    if inputs.get("commitment_made"):
        flags.append("supplier_commitment_refused")

    status = inputs.get("us_fulfillment_evidence_status", "unknown")
    if status not in {"verified", "unverified", "unknown"}:
        status = "unknown"
    epistemic = inputs.get("epistemic_status", "UNKNOWN")
    evidence_ids = list(inputs.get("evidence_ids") or [])
    if status == "verified" and (epistemic != "FACT" or not evidence_ids):
        status = "unknown"
        epistemic = "UNKNOWN"
        flags.append("unverified_supplier_claim_downgraded")

    suppliers = []
    for item in inputs.get("candidate_suppliers") or []:
        copied = dict(item)
        if copied.get("epistemic_status") == "FACT" and not copied.get("evidence_ids"):
            copied["epistemic_status"] = "UNKNOWN"
            copied["notes"] = (
                (copied.get("notes") or "") + " Unsupported FACT downgraded to UNKNOWN."
            ).strip()
            flags.append("unsupported_fact_downgraded")
        suppliers.append(copied)

    if status == "verified" and epistemic == "FACT" and evidence_ids:
        available: Any = True
    elif status == "unknown":
        available = "UNKNOWN"
        epistemic = "UNKNOWN"
    else:
        available = False

    return {
        "candidate_suppliers": suppliers,
        "us_fulfillment_available": available,
        "us_fulfillment_evidence_status": status,
        "statement": inputs.get("statement") or "US fulfillment evidence was not supplied.",
        "epistemic_status": epistemic,
        "evidence_ids": evidence_ids,
        "field": "us_fulfillment",
        "commitment_made": False,
        "external_contact_made": False,
        "validation_flags": flags,
        "notes": "TEST/MOCK screening only. No supplier was contacted and no commitment was made.",
    }
