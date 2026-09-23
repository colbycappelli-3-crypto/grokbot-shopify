"""Unit Economics agent.

Calculates only from supplied numbers. A missing input stays UNKNOWN and blocks
derived profit, margin, and break-even figures.
"""
from __future__ import annotations

from ...gates.rules import compute_unit_economics
from ...protocol.models import Job, make_result
from .common import confidence_for, stage_output


class UnitEconomicsAgent:
    agent_id = "unit_economics_agent"

    def run(self, job: Job, run) -> object:
        market = stage_output(job, "market_research")
        required = list(run.gate_config["gates"]["economics_completeness"]["required_inputs"])
        output = compute_unit_economics(market.get("economics_inputs") or {}, required)
        unknowns = list(output["unknown_inputs"])
        if output.get("break_even_units") == "UNKNOWN":
            unknowns.append("break_even_units")
        level = "low" if unknowns else "medium"
        return make_result(
            job,
            findings=[],
            structured_output=output,
            unknowns=unknowns,
            confidence=confidence_for(
                level,
                "Arithmetic on supplied inputs only. Completeness is not a real-world forecast.",
            ),
            recommended_next_action="proceed" if not output["unknown_inputs"] else "research_further",
        )
