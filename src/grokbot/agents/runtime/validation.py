"""Product Validation agent.

Outcomes are VALIDATE, RESEARCH_FURTHER, or REJECT. The choice comes from the
explicit rules in ``grokbot.gates.rules``, using the market-research handoff.
"""
from __future__ import annotations

from ...gates.rules import decide_product_validation
from ...protocol.models import Job, make_result
from .common import confidence_for, stage_output


class ProductValidationAgent:
    agent_id = "product_validation_agent"

    def run(self, job: Job, run) -> object:
        market = stage_output(job, "market_research")
        decision = decide_product_validation(market, run.gate_config)
        outcome = decision["validation_outcome"]
        action = {"VALIDATE": "proceed", "RESEARCH_FURTHER": "research_further", "REJECT": "reject"}[outcome]
        level = {"VALIDATE": "medium", "RESEARCH_FURTHER": "low", "REJECT": "medium"}[outcome]
        return make_result(
            job,
            findings=[
                {
                    "statement": decision["validation_verdict"]["rationale"],
                    "epistemic_status": "INFERENCE",
                    "evidence_ids": [],
                    "field": "validation_outcome",
                    "notes": "Outcome of explicit rules applied to supplied labels. Not an independent fact.",
                }
            ],
            structured_output=decision,
            unknowns=list(decision["evidence_gaps"]),
            confidence=confidence_for(level, "Explicit validation rules applied to the market-research handoff."),
            recommended_next_action=action,
        )
