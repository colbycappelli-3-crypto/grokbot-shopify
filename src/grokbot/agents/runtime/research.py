"""Read-only research connector agent.

The agent calls mock or unconfigured connectors and copies their labels. It
does not upgrade UNKNOWN to FACT and it does not perform an external action.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ...connectors.registry import ConnectorRegistry
from ...protocol.knowledge import claim, iter_claims
from ...protocol.models import Job, make_result
from .common import confidence_for, fixture_of
from .market import ECONOMICS_KEYS

SUPPLIER_FIELDS = (
    "applicable",
    "us_fulfillment_evidence_status",
    "statement",
    "epistemic_status",
    "evidence_ids",
    "candidate_suppliers",
    "commitment_made",
    "notes",
)
SERVICE_FIELDS = (
    "offer_known",
    "requests_refund",
    "requests_revision",
    "complaint",
    "service_offer",
    "gig_id",
)


class ResearchConnectorAgent:
    agent_id = "research_connector_agent"

    def run(self, job: Job, run) -> object:
        packet = fixture_of(job)
        registry = ConnectorRegistry.load()
        results = _execute_requests(registry, packet)
        output = assemble_research(packet, results)
        unknowns = [item.get("statement", "UNKNOWN") for item in output["unknowns"] if isinstance(item, dict)]
        return make_result(
            job,
            findings=list(output["demand_signals"]),
            structured_output=output,
            evidence=[record["evidence_id"] for record in output["evidence_records"] if "evidence_id" in record],
            assumptions=list(output["assumptions"]),
            unknowns=unknowns,
            confidence=confidence_for(
                "low",
                "Labels were copied from read-only TEST/MOCK connector results and not upgraded.",
            ),
            recommended_next_action="proceed",
        )


def _execute_requests(registry: ConnectorRegistry, packet: Dict[str, Any]) -> List[dict]:
    results = []
    for request in packet.get("connector_requests") or []:
        results.append(
            registry.execute(
                request.get("connector_id", ""),
                request.get("operation", ""),
                request.get("query_id", ""),
            )
        )
    return results


def assemble_research(packet: Dict[str, Any], results: List[dict]) -> Dict[str, Any]:
    niche = claim(
        claim_id="niche-from-packet",
        field="product_niche_hypothesis",
        statement=packet.get("niche_hypothesis") or "No niche hypothesis was supplied.",
        epistemic_status="INFERENCE" if packet.get("niche_hypothesis") else "UNKNOWN",
        notes="Packet text was not upgraded to FACT.",
    )
    output: Dict[str, Any] = {
        "market_summary": niche,
        "niche_hypothesis": niche,
        "business_model": packet.get("business_model") or "UNKNOWN",
        "demand_present": None,
        "demand_present_epistemic_status": "UNKNOWN",
        "demand_present_evidence_ids": [],
        "demand_signals": [],
        "customer_hypothesis": claim(
            claim_id="customer-missing",
            field="target_customer",
            statement="Target customer was not supplied.",
            epistemic_status="UNKNOWN",
        ),
        "competitive_context": claim(
            claim_id="competition-missing",
            field="competition",
            statement="Competitive context was not supplied.",
            epistemic_status="UNKNOWN",
        ),
        "pricing_context": claim(
            claim_id="pricing-missing",
            field="pricing_context",
            statement="Pricing context was not supplied.",
            epistemic_status="UNKNOWN",
        ),
        "seasonality": claim(
            claim_id="seasonality-missing",
            field="seasonality",
            statement="Seasonality was not supplied.",
            epistemic_status="UNKNOWN",
        ),
        "market_risks": [],
        "economics_inputs": {key: None for key in ECONOMICS_KEYS},
        "compliance_inputs": {},
        "supplier_inputs": {},
        "catalog_context": None,
        "assumptions": [
            claim(
                claim_id=f"assumption-{index}",
                field="assumption",
                statement=text,
                epistemic_status="ASSUMPTION",
                notes="Explicit assumption from the TEST/MOCK research packet.",
            )
            for index, text in enumerate(packet.get("assumptions") or [])
        ],
        "unknowns": [],
        "evidence_records": [],
        "connector_results": [],
        "external_actions": [],
        "network_calls": 0,
        "credentials_used": False,
        "production_connected": False,
    }
    for result in results:
        output["connector_results"].append(
            {
                "connector_id": result["connector_id"],
                "operation": result["operation"],
                "query_id": result["query_id"],
                "data_classification": result["data_classification"],
                "refused": result["refused"],
                "refusal_code": result["refusal_code"],
                "network_calls": result["network_calls"],
                "external_actions": [],
                "local_read": result["local_read"],
            }
        )
        output["network_calls"] += int(result.get("network_calls") or 0)
        payload = result.get("payload")
        if result.get("data_classification") != "TEST_MOCK" or not isinstance(payload, dict):
            message = (result.get("unknowns") or ["Connector result is UNKNOWN."])[0]
            output["unknowns"].append(
                claim(
                    claim_id=f"connector-unknown-{result.get('connector_id')}",
                    field="connector_result",
                    statement=message,
                    epistemic_status="UNKNOWN",
                )
            )
            continue
        _apply_payload(output, payload)
        output["evidence_records"].extend(result.get("evidence_records") or [])
    output["unknowns"].extend(
        item for item in iter_claims(output) if item.get("epistemic_status") == "UNKNOWN" and item not in output["unknowns"]
    )
    return output


def _apply_payload(output: Dict[str, Any], payload: Dict[str, Any]) -> None:
    for key in (
        "demand_present",
        "demand_present_epistemic_status",
        "demand_present_evidence_ids",
        "demand_signals",
        "customer_hypothesis",
        "competitive_context",
        "pricing_context",
        "seasonality",
        "market_risks",
    ):
        if key in payload:
            output[key] = payload[key]
    if isinstance(payload.get("niche_hypothesis"), dict):
        output["niche_hypothesis"] = payload["niche_hypothesis"]
        output["market_summary"] = payload["niche_hypothesis"]
    economics = payload.get("economics")
    if isinstance(economics, dict):
        for key in ECONOMICS_KEYS:
            if key in economics:
                output["economics_inputs"][key] = economics[key]
    if isinstance(payload.get("compliance"), dict):
        output["compliance_inputs"] = dict(payload["compliance"])
    if isinstance(payload.get("supplier"), dict):
        output["supplier_inputs"] = dict(payload["supplier"])
    elif "us_fulfillment_evidence_status" in payload:
        output["supplier_inputs"] = {key: payload[key] for key in SUPPLIER_FIELDS if key in payload}
    if "catalog" in payload:
        output["catalog_context"] = payload["catalog"]
    for key in SERVICE_FIELDS:
        if key in payload:
            output[key] = payload[key]
