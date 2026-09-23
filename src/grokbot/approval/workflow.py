"""Human approval workflow for proposed consequential actions.

The owner can see a proposal, approve it, or reject it. An approved,
classified action advances only to ``execution_withheld``. Nothing in this
module publishes, purchases, contacts, messages, orders, refunds, or spends.
Unclassified and prohibited actions stay blocked.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional

from ..clock import utc_now
from ..phase import CONSEQUENTIAL_ACTION_CATEGORIES
from ..policy.approval import ApprovalPolicy
from ..resources import repo_root
from ..validation import SpecValidationError, validate

_UNSET = object()
NEXT_GATE = "execution_withheld"


class ProposalStateError(ValueError):
    pass


def default_approval_dir() -> Path:
    return repo_root() / ".grokbot_state" / "approvals"


def eligibility(policy: ApprovalPolicy, category: str) -> dict:
    """Decide whether a category may be offered for an approval decision.

    Unclassified categories use the policy default and stay blocked. Prohibited
    categories stay blocked. Only a classified approval-required or consequential
    category can later advance, and only as far as the withheld-execution gate.
    """
    decision = policy.classify(category)
    consequential = category in CONSEQUENTIAL_ACTION_CATEGORIES or decision.requires_approval
    if not decision.matched:
        reason = "unclassified_action"
    elif decision.prohibited:
        reason = "prohibited_action"
    elif not consequential:
        reason = "not_a_consequential_action"
    else:
        reason = None
    return {
        "category": category,
        "action_class": decision.action_class.value,
        "classified": decision.matched,
        "consequential": consequential or not decision.matched,
        "block_reason": reason,
        "may_advance": reason is None,
    }


class ApprovalWorkflow:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / "proposals.json"

    def list_items(self) -> List[dict]:
        return list(self._read())

    def get(self, proposal_id: str) -> dict:
        for item in self._read():
            if item["proposal_id"] == proposal_id:
                return item
        raise ProposalStateError(f"Unknown proposal '{proposal_id}'.")

    def propose(
        self,
        *,
        policy: ApprovalPolicy,
        project_id: str,
        workflow_id: str,
        division: str,
        category: str,
        summary: str,
        screening_block: Optional[str] = None,
        data_classification: str = "TEST_MOCK",
        actor: str = "grokbot",
    ) -> dict:
        gate = eligibility(policy, category)
        blocked = gate["block_reason"] is not None
        item = {
            "proposal_id": f"apr-{uuid.uuid4().hex[:12]}",
            "project_id": project_id,
            "workflow_id": workflow_id,
            "division": division,
            "category": category,
            "summary": summary,
            "action_class": gate["action_class"],
            "classified": gate["classified"],
            "consequential": gate["consequential"],
            "status": "blocked" if blocked else "proposed",
            "gate_state": "blocked" if blocked else "awaiting_decision",
            "next_gated_state": None,
            "advanced": False,
            "executed_external_action": False,
            "external_effects": [],
            "block_reason": gate["block_reason"],
            "screening_block": screening_block,
            "decision": None,
            "decision_record": [],
            "data_classification": data_classification,
            "credentials_used": False,
            "network_calls": 0,
            "production_connected": False,
            "created_at": utc_now(),
        }
        _append(
            item,
            "action_proposed",
            actor,
            (
                f"Proposed {category} ({gate['action_class']}). "
                + (
                    f"Blocked: {gate['block_reason']}. "
                    if gate["block_reason"]
                    else "Awaiting an explicit human decision. "
                )
                + "No external action was performed."
            ),
        )
        validate(item, "action_proposal", source=f"proposal:{item['proposal_id']}")
        items = self._read()
        items.append(item)
        self._write(items)
        return item

    def decide(
        self,
        proposal_id: str,
        decision: str,
        note: str = "",
        decided_by: str = "human_owner",
        screening_block: object = _UNSET,
    ) -> dict:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Proposal decision must be 'approved' or 'rejected'.")
        items = self._read()
        target = _find(items, proposal_id)
        if target["status"] in {"approved", "rejected"} or (
            target["status"] == "blocked" and target.get("decision")
        ):
            raise ProposalStateError(f"Proposal '{proposal_id}' is already {target['status']}.")
        reason = target.get("screening_block") if screening_block is _UNSET else screening_block
        recorded = decision
        if target["block_reason"] or (decision == "approved" and reason):
            recorded = "blocked"
            target["status"] = "blocked"
            target["gate_state"] = "blocked"
            target["advanced"] = False
            target["next_gated_state"] = None
            target["block_reason"] = target["block_reason"] or reason
        elif decision == "rejected":
            target["status"] = "rejected"
            target["gate_state"] = "rejected"
            target["advanced"] = False
            target["next_gated_state"] = None
        else:
            target["status"] = "approved"
            target["gate_state"] = "approved_not_executed"
            target["next_gated_state"] = NEXT_GATE
            target["advanced"] = True
            target["block_reason"] = None
        target["executed_external_action"] = False
        target["external_effects"] = []
        target["decision"] = {
            "decision": recorded,
            "note": note,
            "decided_by": decided_by,
            "decided_at": utc_now(),
            "executed_external_action": False,
        }
        _append(
            target,
            "action_decision",
            decided_by,
            f"Decision {recorded} for {target['category']}. No external action was performed.",
        )
        if target["advanced"]:
            _append(
                target,
                "gate_advanced",
                "grokbot",
                f"{target['category']} advanced to {NEXT_GATE}. Execution remains withheld.",
            )
        validate(target, "action_proposal", source=f"proposal:{proposal_id}")
        self._write(items)
        return target

    def release(self, proposal_id: str, actor: str = "grokbot") -> dict:
        """Attempt to leave the approval gate. Phase 4 always withholds execution."""
        items = self._read()
        target = _find(items, proposal_id)
        executed = False
        if target["gate_state"] != "approved_not_executed":
            code = {
                "awaiting_decision": "approval_required",
                "rejected": "approval_rejected",
                "blocked": target.get("block_reason") or "approval_blocked",
            }.get(target["gate_state"], "approval_blocked")
            message = "The action has not been approved, so it did not advance and was not executed."
        else:
            code = "phase_2_offline_no_consequential_actions"
            message = (
                "Approved action reached execution_withheld. "
                "Phase 4 does not publish, purchase, contact, message, order, refund, or spend."
            )
            target["next_gated_state"] = NEXT_GATE
            _append(target, "execution_withheld", actor, message)
        target["executed_external_action"] = False
        target["external_effects"] = []
        target["credentials_used"] = False
        target["network_calls"] = 0
        target["production_connected"] = False
        validate(target, "action_proposal", source=f"proposal:{proposal_id}")
        self._write(items)
        return {
            "proposal_id": proposal_id,
            "category": target["category"],
            "gate_state": target["gate_state"],
            "next_gated_state": target["next_gated_state"],
            "advanced": target["advanced"],
            "executed": executed,
            "executed_external_action": False,
            "external_effects": [],
            "credentials_used": False,
            "network_calls": 0,
            "production_connected": False,
            "code": code,
            "message": message,
        }

    def _read(self) -> List[dict]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ProposalStateError(f"{self.path}: approval store must contain an items list.")
        loaded = []
        for item in items:
            try:
                validate(item, "action_proposal", source=str(self.path))
            except SpecValidationError as exc:
                raise ProposalStateError(str(exc)) from exc
            loaded.append(item)
        return loaded

    def _write(self, items: List[dict]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"items": items}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def present_proposal(item: dict) -> str:
    """Human-readable presentation of one proposed action."""
    lines = [
        f"Proposal:  {item['proposal_id']}",
        f"Project:   {item['project_id']}",
        f"Workflow:  {item['workflow_id']} ({item['division']})",
        f"Category:  {item['category']}",
        f"Class:     {item['action_class']}",
        f"Classified:{item['classified']}",
        f"Status:    {item['status']}",
        f"Gate:      {item['gate_state']}",
        f"Next gate: {item['next_gated_state'] or '(not advanced)'}",
        f"Summary:   {item['summary']}",
        f"Data:      {item['data_classification']}",
        "Execution: withheld. credentials_used=false network_calls=0 production_connected=false",
    ]
    if item.get("block_reason"):
        lines.append(f"Blocked:   {item['block_reason']}")
    if item.get("screening_block"):
        lines.append(f"Screening: {item['screening_block']} prevents advancement.")
    decision = item.get("decision") or {}
    if decision:
        lines.append(
            f"Decision:  {decision['decision']} by {decision['decided_by']} "
            f"executed_external_action={decision['executed_external_action']}"
        )
    lines.append("Record:")
    for entry in item["decision_record"]:
        lines.append(f"  - {entry['event']}: {entry['summary']}")
    return "\n".join(lines)


def _append(item: dict, event: str, actor: str, summary: str) -> None:
    item["decision_record"].append(
        {
            "timestamp": utc_now(),
            "event": event,
            "actor": actor,
            "summary": summary,
            "executed_external_action": False,
        }
    )


def demonstrate_approval_workflow(directory: Path) -> dict:
    """Run the approval workflow against TEST/MOCK research. Nothing external happens."""
    from ..fixtures.loader import load_research_packet
    from ..orchestrator.engine import build_runner

    packet = load_research_packet("pod_research_ready")
    runner = build_runner()
    run = runner.open_opportunity(packet["objective"], workflow_id=packet["workflow_id"], fixture=packet)
    runner.run(run)
    store = ApprovalWorkflow(directory)
    launch = runner.propose_consequential_action(
        run,
        store,
        "launch_store",
        "TEST/MOCK proposal: launch a store for the constellation-cat drafts. The store would not be created.",
    )
    contact = runner.propose_consequential_action(
        run,
        store,
        "contact_supplier",
        "TEST/MOCK proposal: contact a supplier about fulfillment. No supplier would be contacted.",
    )
    unknown = runner.propose_consequential_action(
        run,
        store,
        "product_publication",
        "TEST/MOCK proposal: publish the shirt draft. This category is unclassified and must stay blocked.",
    )
    prohibited = runner.propose_consequential_action(
        run,
        store,
        "ip_infringement",
        "TEST/MOCK proposal: use a protected design. This category is prohibited.",
    )
    contact = runner.decide_consequential_action(run, store, contact["proposal_id"], "rejected", note="do not contact")
    launch = runner.decide_consequential_action(run, store, launch["proposal_id"], "approved", note="advance the gate only")
    unknown = runner.decide_consequential_action(run, store, unknown["proposal_id"], "approved", note="must not advance")
    prohibited = runner.decide_consequential_action(
        run, store, prohibited["proposal_id"], "approved", note="must not advance"
    )
    released = runner.release_consequential_action(run, store, launch["proposal_id"])
    rejected_release = runner.release_consequential_action(run, store, contact["proposal_id"])
    ok = (
        launch["advanced"] is True
        and launch["gate_state"] == "approved_not_executed"
        and launch["next_gated_state"] == NEXT_GATE
        and launch["executed_external_action"] is False
        and contact["advanced"] is False
        and contact["gate_state"] == "rejected"
        and unknown["advanced"] is False
        and unknown["block_reason"] == "unclassified_action"
        and prohibited["advanced"] is False
        and prohibited["block_reason"] == "prohibited_action"
        and released["executed"] is False
        and released["code"] == "phase_2_offline_no_consequential_actions"
        and released["external_effects"] == []
        and rejected_release["executed"] is False
        and rejected_release["code"] == "approval_rejected"
        and run.external_actions_performed == []
    )
    lines = [
        present_proposal(store.get(launch["proposal_id"])),
        "",
        present_proposal(store.get(contact["proposal_id"])),
        "",
        present_proposal(store.get(unknown["proposal_id"])),
        "",
        present_proposal(store.get(prohibited["proposal_id"])),
        "",
        f"Release approved action: executed={released['executed']} code={released['code']}",
        f"Release rejected action: executed={rejected_release['executed']} code={rejected_release['code']}",
        f"External actions performed: {len(run.external_actions_performed)}",
    ]
    return {"ok": ok, "text": "\n".join(lines), "run": run, "released": released}


def _find(items: List[dict], proposal_id: str) -> dict:
    for item in items:
        if item["proposal_id"] == proposal_id:
            return item
    raise ProposalStateError(f"Unknown proposal '{proposal_id}'.")
