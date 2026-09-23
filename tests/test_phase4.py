"""Phase 4 human approval workflow. Decisions are recorded. Actions are not executed."""
from grokbot.approval.workflow import ApprovalWorkflow, demonstrate_approval_workflow, eligibility
from grokbot.cli import main
from grokbot.fixtures.loader import load_fixture, load_research_packet
from grokbot.orchestrator.engine import build_runner
from grokbot.phase import EXTERNAL_CONNECTIONS_ENABLED
from grokbot.policy.approval import load_default_policy


def _ready_run():
    packet = load_research_packet("pod_research_ready")
    runner = build_runner()
    run = runner.open_opportunity(packet["objective"], workflow_id=packet["workflow_id"], fixture=packet)
    runner.run(run)
    return runner, run


def test_external_systems_stay_disconnected():
    assert EXTERNAL_CONNECTIONS_ENABLED is False


def test_unclassified_and_prohibited_actions_cannot_advance(tmp_path):
    policy = load_default_policy()
    assert eligibility(policy, "product_publication")["block_reason"] == "unclassified_action"
    assert eligibility(policy, "not_a_known_category")["block_reason"] == "unclassified_action"
    assert eligibility(policy, "ip_infringement")["block_reason"] == "prohibited_action"
    assert eligibility(policy, "market_research")["block_reason"] == "not_a_consequential_action"
    assert eligibility(policy, "launch_store")["may_advance"] is True

    runner, run = _ready_run()
    store = ApprovalWorkflow(tmp_path)
    unknown = runner.propose_consequential_action(
        run, store, "product_publication", "TEST/MOCK publish proposal that must stay blocked."
    )
    decided = runner.decide_consequential_action(run, store, unknown["proposal_id"], "approved", note="try")
    assert decided["advanced"] is False
    assert decided["gate_state"] == "blocked"
    assert decided["next_gated_state"] is None
    assert decided["decision"]["executed_external_action"] is False
    released = runner.release_consequential_action(run, store, unknown["proposal_id"])
    assert released["executed"] is False
    assert released["external_effects"] == []
    assert run.external_actions_performed == []


def test_reject_does_not_advance_and_approval_advances_only_to_withheld_execution(tmp_path):
    runner, run = _ready_run()
    store = ApprovalWorkflow(tmp_path)
    launch = runner.propose_consequential_action(
        run,
        store,
        "launch_store",
        "TEST/MOCK proposal to launch a store. It must not be launched.",
    )
    contact = runner.propose_consequential_action(
        run,
        store,
        "contact_supplier",
        "TEST/MOCK proposal to contact a supplier. It must not be sent.",
    )
    assert launch["gate_state"] == "awaiting_decision"
    assert launch["decision_record"][0]["event"] == "action_proposed"
    rejected = runner.decide_consequential_action(run, store, contact["proposal_id"], "rejected", note="no")
    assert rejected["advanced"] is False
    assert rejected["gate_state"] == "rejected"
    assert rejected["next_gated_state"] is None
    approved = runner.decide_consequential_action(run, store, launch["proposal_id"], "approved", note="gate only")
    assert approved["advanced"] is True
    assert approved["status"] == "approved"
    assert approved["gate_state"] == "approved_not_executed"
    assert approved["next_gated_state"] == "execution_withheld"
    assert approved["executed_external_action"] is False
    assert any(entry["event"] == "gate_advanced" for entry in approved["decision_record"])
    assert run.audit.of_type("action_proposed")
    assert run.audit.of_type("action_decision")
    assert run.audit.of_type("gate_advanced")

    withheld = runner.release_consequential_action(run, store, launch["proposal_id"])
    assert withheld["executed"] is False
    assert withheld["code"] == "phase_2_offline_no_consequential_actions"
    assert withheld["credentials_used"] is False
    assert withheld["network_calls"] == 0
    assert withheld["production_connected"] is False
    still_blocked = runner.attempt_action(run, "launch_store")
    assert still_blocked["executed"] is False
    assert any(reason["code"] == "phase_2_offline_no_consequential_actions" for reason in still_blocked["reasons"])
    rejected_release = runner.release_consequential_action(run, store, contact["proposal_id"])
    assert rejected_release["executed"] is False
    assert rejected_release["code"] == "approval_rejected"
    assert run.external_actions_performed == []


def test_unresolved_screening_blocks_advancement(tmp_path):
    fixture = load_fixture("attractive_economics_ip_risk")
    runner = build_runner()
    run = runner.open_opportunity(fixture["objective"], workflow_id=fixture["workflow_id"], fixture=fixture)
    runner.run(run)
    store = ApprovalWorkflow(tmp_path)
    proposal = runner.propose_consequential_action(
        run,
        store,
        "launch_store",
        "TEST/MOCK proposal while IP risk is unresolved.",
    )
    assert proposal["screening_block"] == "unresolved_ip_risk"
    decided = runner.decide_consequential_action(run, store, proposal["proposal_id"], "approved", note="try")
    assert decided["advanced"] is False
    assert decided["decision"]["decision"] == "blocked"
    assert decided["block_reason"] == "unresolved_ip_risk"
    assert decided["executed_external_action"] is False
    assert run.external_actions_performed == []


def test_mock_approval_demo_command(tmp_path):
    assert main(["approve", "demo"]) == 0
    report = demonstrate_approval_workflow(tmp_path / "demo")
    assert report["ok"] is True
    assert report["released"]["executed"] is False
