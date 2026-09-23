"""Compliance / IP screening agent.

Flags supplied risk labels for review. It does not give legal advice, query a
register, or clear an unresolved trademark or copyright question.
"""
from __future__ import annotations

from ...gates.rules import screen_compliance
from ...protocol.models import Job, make_result
from .common import confidence_for, stage_output


class ComplianceScreeningAgent:
    agent_id = "compliance_ip_screening_agent"

    def run(self, job: Job, run) -> object:
        market = stage_output(job, "market_research")
        output = screen_compliance(market.get("compliance_inputs") or {})
        action = "proceed" if output["recommendation"] == "clear" else "stop_unresolved_risk"
        return make_result(
            job,
            findings=list(output["risk_findings"]),
            structured_output=output,
            evidence=[
                evidence_id
                for finding in output["risk_findings"]
                for evidence_id in (finding.get("evidence_ids") or [])
            ],
            unknowns=[name for name in output["blocking_fields"] if output.get(name) == "UNKNOWN"],
            confidence=confidence_for(
                "low",
                "Screening of supplied flags only. Not a legal conclusion.",
            ),
            recommended_next_action=action,
        )
