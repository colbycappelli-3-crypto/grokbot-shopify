"""Evaluate configured validation gates.

A failed gate returns machine-readable reason codes. Margin threshold is
applied only when gross margin was actually computed.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .rules import critical_unknown_fields, verified_demand_count


def _reason(code: str, message: str, *, severity: str = "fail", **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"code": code, "message": message, "severity": severity}
    payload.update(extra)
    return payload


def _info(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    return _reason(code, message, severity="info", **extra)


def build_gate_context(run: Any) -> Dict[str, Any]:
    market = run.outputs.get("market_research") or {}
    validation = run.outputs.get("product_validation") or {}
    economics = run.outputs.get("unit_economics") or {}
    compliance = run.outputs.get("compliance_screen") or {}
    supplier = run.outputs.get("supplier_evidence") or {}
    service = run.outputs.get("service_research") or {}
    communication = run.outputs.get("communication_draft") or {}
    service_workflow = run.outputs.get("service_workflow") or {}
    critical = list(
        run.gate_config["gates"]["excessive_unknown_critical_fields"]["critical_fields"]
    )
    margin = economics.get("gross_margin", "UNKNOWN")
    return {
        "division": run.workflow.division,
        "market": market,
        "validation_outcome": validation.get("validation_outcome"),
        "failed_criteria": list(validation.get("failed_criteria") or []),
        "verified_demand_signals": verified_demand_count(market),
        "configured_minimum_demand_signals": run.gate_config["gates"]["minimum_evidence_completeness"][
            "min_verified_demand_signals"
        ],
        "unknown_critical_fields": critical_unknown_fields(market, critical),
        "economics": economics,
        "gross_margin": margin if isinstance(margin, (int, float)) else None,
        "compliance": compliance,
        "supplier": supplier,
        "service": service,
        "communication": communication,
        "service_workflow": service_workflow,
    }


def evaluate_gate(gate_id: str, context: Dict[str, Any], gate_config: Dict[str, Any]) -> Dict[str, Any]:
    spec = gate_config["gates"][gate_id]
    reasons = _evaluate(gate_id, spec, context)
    applicable = not any(reason["code"].endswith("_not_applicable") for reason in reasons)
    passed = not any(reason["severity"] == "fail" for reason in reasons)
    return {
        "gate_id": gate_id,
        "passed": passed,
        "applicable": applicable,
        "reasons": reasons,
    }


def _evaluate(gate_id: str, spec: Dict[str, Any], context: Dict[str, Any]) -> List[dict]:
    if gate_id == "minimum_evidence_completeness":
        found = context["verified_demand_signals"]
        needed = spec["min_verified_demand_signals"]
        if found < needed:
            return [
                _reason(
                    "insufficient_verified_demand_evidence",
                    f"Verified demand signals ({found}) are below the configured minimum ({needed}).",
                    field="demand",
                    observed=found,
                    threshold=needed,
                )
            ]
        return []

    if gate_id == "excessive_unknown_critical_fields":
        unknown = list(context["unknown_critical_fields"])
        if len(unknown) > spec["max_unknown"]:
            return [
                _reason(
                    "excessive_unknown_critical_fields",
                    "UNKNOWN critical fields: " + ", ".join(unknown) + f". Configured max_unknown is {spec['max_unknown']}.",
                    field="critical_fields",
                    observed=unknown,
                    threshold=spec["max_unknown"],
                )
            ]
        return []

    if gate_id == "product_validation_outcome":
        outcome = context.get("validation_outcome")
        reasons = []
        if outcome != spec["required_outcome"]:
            reasons.append(
                _reason(
                    "validation_outcome_not_validate",
                    f"Product validation outcome is {outcome or 'UNKNOWN'}, not {spec['required_outcome']}.",
                    field="validation_outcome",
                    observed=outcome or "UNKNOWN",
                )
            )
            for item in context.get("failed_criteria") or []:
                reasons.append(
                    _reason(
                        item.get("code", "validation_criterion_failed"),
                        item.get("message", "Validation criterion failed."),
                    )
                )
        elif context["verified_demand_signals"] < context.get("configured_minimum_demand_signals", 1):
            reasons.append(
                _reason(
                    "agent_outcome_contradicts_evidence",
                    "Product validation returned VALIDATE without the configured minimum of verified demand evidence.",
                    field="demand",
                    observed=context["verified_demand_signals"],
                    threshold=context.get("configured_minimum_demand_signals"),
                )
            )
        return reasons

    if gate_id == "economics_completeness":
        economics = context.get("economics") or {}
        reasons = []
        if not economics:
            return [
                _reason(
                    "economics_not_assessed",
                    "Unit economics has not been assessed.",
                    field="unit_economics",
                    observed="UNKNOWN",
                )
            ]
        for name in spec["required_inputs"]:
            if economics.get(name) in (None, "UNKNOWN"):
                reasons.append(
                    _reason(
                        "economics_input_unknown",
                        f"Economics input '{name}' is UNKNOWN. It was not invented.",
                        field=name,
                        observed="UNKNOWN",
                    )
                )
        return reasons

    if gate_id == "margin_threshold":
        if not spec.get("applies_only_when_computable", True):
            return [_reason("margin_threshold_misconfigured", "Gate configuration is inconsistent.")]
        margin = context.get("gross_margin")
        if margin is None:
            return [
                _info(
                    "margin_threshold_not_applicable",
                    "Gross margin is UNKNOWN, so the configured margin threshold was not treated as passed or failed.",
                    field="gross_margin",
                    observed="UNKNOWN",
                    threshold=spec["min_gross_margin"],
                )
            ]
        if margin < spec["min_gross_margin"]:
            return [
                _reason(
                    "margin_below_configured_threshold",
                    (
                        f"Computed gross margin {margin:.4f} is below the configured "
                        f"default min_gross_margin {spec['min_gross_margin']}."
                    ),
                    field="gross_margin",
                    observed=margin,
                    threshold=spec["min_gross_margin"],
                )
            ]
        return []

    if gate_id == "unresolved_ip_risk":
        compliance = context.get("compliance") or {}
        reasons = []
        blocking = set(spec["blocking_statuses"])
        if not compliance:
            return [
                _reason(
                    "unresolved_ip_risk",
                    "IP screening has not produced a clear result.",
                    field="ip_screening",
                    observed="UNKNOWN",
                )
            ]
        for name in spec["fields"]:
            observed = compliance.get(name, "UNKNOWN")
            if observed in blocking:
                reasons.append(
                    _reason(
                        "unresolved_ip_risk",
                        f"{name} is {observed}. Automatic approval stays blocked until this is resolved.",
                        field=name,
                        observed=observed,
                    )
                )
        return reasons

    if gate_id == "unresolved_prohibited_product_risk":
        compliance = context.get("compliance") or {}
        observed = (compliance or {}).get(spec["field"], "UNKNOWN")
        if not compliance or observed in set(spec["blocking_statuses"]):
            return [
                _reason(
                    "unresolved_prohibited_product_risk",
                    f"{spec['field']} is {observed}.",
                    field=spec["field"],
                    observed=observed,
                )
            ]
        return []

    if gate_id == "supplier_evidence_requirement":
        if context.get("division") not in spec["applies_to_divisions"]:
            return [
                _info(
                    "supplier_evidence_requirement_not_applicable",
                    "This division does not require the dropshipping supplier-evidence gate.",
                )
            ]
        supplier = context.get("supplier") or {}
        observed = supplier.get("us_fulfillment_evidence_status", "unknown")
        if observed != spec["required_status"]:
            return [
                _reason(
                    "us_fulfillment_evidence_missing",
                    (
                        "Verified US fulfillment evidence is required for this dropshipping "
                        f"workflow. Observed status is '{observed}'."
                    ),
                    field="us_fulfillment_evidence_status",
                    observed=observed,
                    threshold=spec["required_status"],
                )
            ]
        return []

    if gate_id == "service_delivery_readiness":
        if context.get("division") not in spec["applies_to_divisions"]:
            return [
                _info(
                    "service_delivery_readiness_not_applicable",
                    "This division does not use the digital-services delivery gate.",
                )
            ]
        service = context.get("service") or {}
        communication = context.get("communication") or {}
        workflow = context.get("service_workflow") or {}
        sent = any(
            source.get("message_sent") is True for source in (service, communication, workflow)
        )
        refunded = any(
            source.get("refund_issued") is True for source in (service, communication, workflow)
        )
        if sent or refunded:
            return [
                _reason(
                    "consequential_service_action_recorded",
                    "A message send or refund was recorded. The gate fails closed and does not continue.",
                    field="message_sent" if sent else "refund_issued",
                    observed=True,
                )
            ]
        if service.get("requests_refund") is True or service.get("complaint") is True:
            return [
                _reason(
                    "service_refund_request_requires_escalation",
                    "A refund or complaint request is present. No refund was issued and no message was sent.",
                    field="requests_refund" if service.get("requests_refund") else "complaint",
                    observed=True,
                )
            ]
        if service.get("offer_known") is not True:
            return [
                _reason(
                    "service_offer_unknown",
                    "The service offer is UNKNOWN. No offer was invented.",
                    field="service_offer",
                    observed="UNKNOWN",
                )
            ]
        return []

    return [_reason("unknown_gate", f"No evaluator is registered for gate '{gate_id}'.")]


def select_on_fail(default: str, evaluations: List[dict], validation_outcome: str | None) -> str:
    """Pick the workflow stop policy from the failed reason codes."""
    codes = {
        reason["code"]
        for evaluation in evaluations
        for reason in evaluation["reasons"]
        if reason["severity"] == "fail"
    }
    if "consequential_service_action_recorded" in codes:
        return "halt"
    if "service_refund_request_requires_escalation" in codes:
        return "escalate"
    if "service_offer_unknown" in codes:
        return "request_more_research"
    if validation_outcome == "REJECT" or "verified_demand_absent" in codes or "prohibited_product_confirmed" in codes:
        return "reject"
    if (
        validation_outcome == "RESEARCH_FURTHER"
        or "demand_evidence_incomplete" in codes
        or "excessive_unknown_critical_fields" in codes
        or "insufficient_verified_demand_evidence" in codes
        or "us_fulfillment_evidence_missing" in codes
        or "agent_outcome_contradicts_evidence" in codes
    ):
        return "request_more_research"
    if "unresolved_ip_risk" in codes or "unresolved_prohibited_product_risk" in codes:
        return "escalate"
    return default
