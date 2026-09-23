"""Digital-services research, workflow, and communication drafts.

Drafts are not sent. Orders are not placed. Refunds are not issued.
"""
from __future__ import annotations

from typing import Any, Dict

from ...connectors.registry import ConnectorRegistry
from ...protocol.knowledge import claim
from ...protocol.models import Job, make_result
from .common import confidence_for, fixture_of, stage_output
from .research import _execute_requests, assemble_research


class ServiceResearchAgent:
    agent_id = "service_research_agent"

    def run(self, job: Job, run) -> object:
        packet = fixture_of(job)
        output = assemble_research(packet, _execute_requests(ConnectorRegistry.load(), packet))
        _seal_service(output)
        action = "proceed" if output.get("offer_known") is True else "research_further"
        return make_result(
            job,
            findings=[output.get("service_offer") or output["niche_hypothesis"]],
            structured_output=output,
            evidence=[record["evidence_id"] for record in output["evidence_records"] if "evidence_id" in record],
            assumptions=list(output["assumptions"]),
            unknowns=[item.get("statement", "UNKNOWN") for item in output["unknowns"] if isinstance(item, dict)],
            confidence=confidence_for("low", "TEST/MOCK service research. No Fiverr account was contacted."),
            recommended_next_action=action,
        )


class ServiceWorkflowAgent:
    agent_id = "service_workflow_agent"

    def run(self, job: Job, run) -> object:
        service = stage_output(job, "service_research")
        output = build_service_workflow(service)
        return make_result(
            job,
            findings=list(output["tasks"]),
            structured_output=output,
            confidence=confidence_for("low", "Local task state only. No delivery was sent."),
            recommended_next_action="proceed",
        )


class ServiceCommunicationDraftAgent:
    agent_id = "service_communication_draft_agent"

    def run(self, job: Job, run) -> object:
        service = stage_output(job, "service_research")
        output = build_communication_draft(service)
        return make_result(
            job,
            findings=[output["draft"]],
            structured_output=output,
            confidence=confidence_for("low", "Message draft only. Nothing was sent and no refund was issued."),
            recommended_next_action=output["recommended_disposition"],
        )


def _seal_service(output: Dict[str, Any]) -> None:
    for key in ("message_sent", "refund_issued", "order_placed", "customer_contacted"):
        if output.get(key) is True:
            output.setdefault("validation_flags", []).append(f"{key}_forced_false")
        output[key] = False
    output["external_actions"] = []
    output["network_calls"] = 0
    output["credentials_used"] = False
    if not isinstance(output.get("service_offer"), dict):
        output["service_offer"] = claim(
            claim_id="service-offer-missing",
            field="service_offer",
            statement="Service offer was not supplied.",
            epistemic_status="UNKNOWN",
        )


def build_service_workflow(service: Dict[str, Any]) -> Dict[str, Any]:
    complaint = bool(service.get("requests_refund") or service.get("complaint"))
    return {
        "project_state": "prepared_not_delivered",
        "tasks": [
            {"task_id": "intake", "status": "prepared"},
            {"task_id": "delivery_draft", "status": "draft"},
            {"task_id": "customer_message", "status": "not_sent"},
            {"task_id": "refund", "status": "not_issued" if complaint else "not_requested"},
        ],
        "message_sent": False,
        "refund_issued": False,
        "order_placed": False,
        "external_actions": [],
        "network_calls": 0,
        "credentials_used": False,
    }


def build_communication_draft(service: Dict[str, Any]) -> Dict[str, Any]:
    complaint = bool(service.get("requests_refund") or service.get("complaint"))
    if complaint:
        statement = "TEST/MOCK complaint response draft. This message was not sent. No refund was issued."
        disposition = "escalate_to_human"
    elif service.get("requests_revision") is True:
        statement = "TEST/MOCK revision draft. This message was not sent."
        disposition = "proceed"
    else:
        statement = "TEST/MOCK service message draft. This message was not sent."
        disposition = "proceed"
    return {
        "draft": claim(
            claim_id="service-draft",
            field="customer_message_draft",
            statement=statement,
            epistemic_status="ASSUMPTION",
            notes="Draft text is not a sent message.",
        ),
        "message_sent": False,
        "refund_issued": False,
        "order_placed": False,
        "requires_human_approval_to_send": True,
        "recommended_disposition": disposition,
        "external_actions": [],
        "network_calls": 0,
        "credentials_used": False,
    }
