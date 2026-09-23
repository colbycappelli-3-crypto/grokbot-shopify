"""Draft-only product and listing agents.

Drafts are not published, stores are not launched, and suppliers are not contacted.
"""
from __future__ import annotations

from typing import Any, Dict

from ...protocol.knowledge import claim
from ...protocol.models import Job, make_result
from .common import confidence_for, stage_output


class PodProductDraftAgent:
    agent_id = "pod_product_draft_agent"

    def run(self, job: Job, run) -> object:
        output = build_pod_drafts(stage_output(job, "market_research"))
        return make_result(
            job,
            findings=list(output["drafts"]),
            structured_output=output,
            assumptions=list(output["drafts"]),
            confidence=confidence_for("low", "Draft text only. Nothing was published or written to a catalog."),
            recommended_next_action="proceed",
        )


class ListingDraftAgent:
    agent_id = "listing_draft_agent"

    def run(self, job: Job, run) -> object:
        output = build_listing_draft(
            stage_output(job, "market_research"),
            stage_output(job, "supplier_evidence"),
        )
        action = "proceed" if output["shipping_claim"]["epistemic_status"] != "UNKNOWN" else "research_further"
        return make_result(
            job,
            findings=[output["shipping_claim"]],
            structured_output=output,
            unknowns=[] if action == "proceed" else ["shipping_speed"],
            confidence=confidence_for("low", "Listing draft only. No Shopify write and no supplier contact."),
            recommended_next_action=action,
        )


def build_pod_drafts(market: Dict[str, Any]) -> Dict[str, Any]:
    niche = market.get("niche_hypothesis") or {}
    label = niche.get("statement") if isinstance(niche, dict) else "UNKNOWN"
    catalog = market.get("catalog_context") or {}
    drafts = []
    for kind in ("shirt", "hat"):
        drafts.append(
            {
                "product_kind": kind,
                "title": f"TEST/MOCK draft {kind} — {label}",
                "publish_status": "not_published",
                "epistemic_status": "ASSUMPTION",
                "statement": "Draft only. Nothing was written to a Shopify catalog or published.",
                "evidence_ids": [],
                "field": "product_draft",
            }
        )
    flagged = bool(catalog.get("production_connected"))
    return {
        "drafts": drafts,
        "store_launched": False,
        "catalog_written": False,
        "publish_status": "not_published",
        "production_connected": False,
        "catalog_reported_production_connected": flagged,
        "validation_flags": ["production_connection_ignored"] if flagged else [],
        "external_actions": [],
        "network_calls": 0,
        "credentials_used": False,
    }


def build_listing_draft(market: Dict[str, Any], supplier: Dict[str, Any]) -> Dict[str, Any]:
    verified = (
        supplier.get("us_fulfillment_evidence_status") == "verified"
        and supplier.get("epistemic_status") == "FACT"
        and bool(supplier.get("evidence_ids"))
    )
    niche = market.get("niche_hypothesis") or {}
    label = niche.get("statement") if isinstance(niche, dict) else "UNKNOWN"
    if verified:
        shipping = claim(
            claim_id="shipping-inference",
            field="shipping_speed",
            statement=(
                "TEST/MOCK US warehouse evidence is present. Transit time was not measured, "
                "so fast shipping is not a FACT."
            ),
            epistemic_status="INFERENCE",
            notes="Warehouse label is not a measured transit time.",
        )
    else:
        shipping = claim(
            claim_id="shipping-unknown",
            field="shipping_speed",
            statement="US fulfillment is UNKNOWN. Fast domestic shipping is not claimed.",
            epistemic_status="UNKNOWN",
        )
    return {
        "title": f"TEST/MOCK listing draft — {label}",
        "listing_published": False,
        "store_launched": False,
        "catalog_written": False,
        "publish_status": "not_published",
        "commitment_made": False,
        "supplier_contacted": False,
        "shipping_claim": shipping,
        "external_actions": [],
        "network_calls": 0,
        "credentials_used": False,
    }
