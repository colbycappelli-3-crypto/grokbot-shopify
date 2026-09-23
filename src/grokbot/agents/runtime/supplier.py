"""Supplier evidence agent.

Reports preliminary fulfillment evidence from the handoff. It does not contact
suppliers or record a commitment.
"""
from __future__ import annotations

from ...gates.rules import assess_supplier
from ...protocol.models import Job, make_result
from .common import confidence_for, stage_output


class SupplierResearchAgent:
    agent_id = "supplier_research_agent"

    def run(self, job: Job, run) -> object:
        market = stage_output(job, "market_research")
        output = assess_supplier(market.get("supplier_inputs") or {})
        unknowns = []
        if output["epistemic_status"] == "UNKNOWN" or output["us_fulfillment_available"] == "UNKNOWN":
            unknowns.append("us_fulfillment")
        return make_result(
            job,
            findings=[
                {
                    "statement": output["statement"],
                    "epistemic_status": output["epistemic_status"],
                    "evidence_ids": list(output["evidence_ids"]),
                    "field": "us_fulfillment",
                    "notes": output["notes"],
                }
            ],
            structured_output=output,
            evidence=list(output["evidence_ids"]),
            unknowns=unknowns,
            validation_flags=list(output["validation_flags"]),
            confidence=confidence_for(
                "low",
                "Restated supplied TEST/MOCK fulfillment evidence. No supplier was contacted.",
            ),
            recommended_next_action="proceed" if output["us_fulfillment_evidence_status"] == "verified" else "research_further",
        )
