"""Trend Discovery agent.

Identifies candidate niches from the supplied TEST/MOCK packet. A candidate is
never treated as a successful opportunity just because it was supplied.
"""
from __future__ import annotations

from ...protocol.models import Job, make_result
from .common import confidence_for, fixture_of


class TrendDiscoveryAgent:
    agent_id = "trend_discovery_agent"

    def run(self, job: Job, run) -> object:
        fixture = fixture_of(job)
        candidates = list(fixture.get("candidates") or [])
        opportunities = []
        unknowns = []
        research = []
        for candidate in candidates:
            opportunities.append(
                {
                    "candidate_id": candidate.get("candidate_id", "unknown-candidate"),
                    "theme": candidate.get("theme", "UNKNOWN"),
                    "category": candidate.get("category", "UNKNOWN"),
                    "field": "candidate_opportunity",
                    "statement": candidate.get("statement")
                    or "TEST/MOCK candidate. A supplied theme is not a successful opportunity.",
                    "epistemic_status": candidate.get("epistemic_status", "UNKNOWN"),
                    "evidence_ids": list(candidate.get("evidence_ids") or []),
                    "notes": "A candidate is not a declaration that the opportunity succeeded.",
                }
            )
            unknowns.extend(candidate.get("unknowns") or [])
            research.extend(candidate.get("recommended_research") or [])
        if not opportunities:
            unknowns.append("No candidate was supplied in the TEST/MOCK packet.")
            research.append("Supply a candidate niche before treating research as specific.")
        output = {
            "candidate_opportunities": opportunities,
            "evidence_requirements": [
                "At least one demand signal with verified evidence before validation.",
                "Target customer, competition, and pricing context, each labeled FACT, INFERENCE, ASSUMPTION, or UNKNOWN.",
            ],
            "unknowns": unknowns,
            "recommended_research": research,
            "declares_opportunity_successful": False,
        }
        return make_result(
            job,
            findings=opportunities,
            structured_output=output,
            evidence=[evidence_id for item in opportunities for evidence_id in item["evidence_ids"]],
            unknowns=unknowns,
            confidence=confidence_for(
                "low",
                "Candidates were copied from the TEST/MOCK packet. Trend presence is not success.",
            ),
            recommended_next_action="proceed_to_market_research" if opportunities else "research_further",
        )
