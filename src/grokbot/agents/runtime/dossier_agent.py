"""Dossier agent.

Aggregates upstream structured outputs. It does not add evidence or clear
failed gates.
"""
from __future__ import annotations

from ...dossier.builder import build_dossier
from ...protocol.models import Job, make_result
from .common import confidence_for


class OpportunityDossierAgent:
    agent_id = "opportunity_dossier_agent"

    def run(self, job: Job, run) -> object:
        dossier = build_dossier(run)
        run.dossier = dossier
        return make_result(
            job,
            findings=[],
            structured_output={
                "dossier_id": dossier["dossier_id"],
                "project_id": dossier["project_id"],
                "data_classification": dossier["data_classification"],
            },
            confidence=confidence_for(
                "not_applicable",
                "Aggregation of prior agent outputs, evidence, and gate results.",
            ),
            recommended_next_action="await_human_review",
        )
