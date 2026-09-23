"""Phase 3 human review, read-only connectors, and division research."""
import json
import os
import threading

import http.client

from grokbot.agents.runtime.drafts import build_listing_draft
from grokbot.cli import main
from grokbot.connectors.registry import ConnectorRegistry, UnconfiguredReadOnlyConnector
from grokbot.fixtures.loader import load_research_packet
from grokbot.gates.evaluator import build_gate_context, evaluate_gate, select_on_fail
from grokbot.gates.loader import load_validation_gates
from grokbot.orchestrator.engine import build_runner
from grokbot.phase import EXTERNAL_CONNECTIONS_ENABLED, PHASE
from grokbot.review.queue import ReviewQueue
from grokbot.review.surface import render_reviews, serve_reviews


def _research(packet_id, queue=None):
    packet = load_research_packet(packet_id)
    runner = build_runner()
    run = runner.open_opportunity(packet["objective"], workflow_id=packet["workflow_id"], fixture=packet)
    runner.run(run, review_queue=queue)
    return runner, run


def test_phase_keeps_external_connections_disabled():
    assert PHASE == "phase_3_review_research"
    assert EXTERNAL_CONNECTIONS_ENABLED is False


def test_connectors_are_mock_or_read_only_and_forbid_external_operations():
    registry = ConnectorRegistry.load()
    assert len(registry) == 4
    for spec in registry.specs.values():
        assert spec["mode"] in {"mock", "read_only"}
        assert spec["access"] == "read_only"
        assert spec["credentials_required"] is False
        assert spec["production_connected"] is False
    refused = registry.execute("mock_market_signals", "purchase", "pod-shirt-ready")
    assert refused["refused"] is True
    assert refused["executed"] is False
    assert refused["external_actions"] == []
    assert refused["network_calls"] == 0
    assert refused["payload"] is None
    blob = json.dumps(refused)
    assert "constellation-cat" not in blob


def test_unknown_query_stays_unknown():
    result = ConnectorRegistry.load().execute("mock_market_signals", "search", "no-such-query")
    assert result["data_classification"] == "UNKNOWN"
    assert result["payload"] is None
    assert result["external_actions"] == []
    assert result["network_calls"] == 0
    assert result["executed"] is False


def test_unconfigured_read_only_connector_does_not_leak_environment_secrets():
    os.environ["GROKBOT_TEST_SECRET"] = "super-secret-token-xyz"
    connector = UnconfiguredReadOnlyConnector()
    result = connector.execute("search", "anything")
    blob = json.dumps(result)
    assert "super-secret-token-xyz" not in blob
    assert os.environ["GROKBOT_TEST_SECRET"] not in blob
    assert result["network_calls"] == 0
    assert result["credentials_used"] is False
    assert result["data_classification"] == "UNKNOWN"
    assert result["external_actions"] == []
    refused = connector.execute("send_message", "super-secret-token-xyz")
    assert refused["external_actions"] == []
    assert refused["executed"] is False
    assert "super-secret-token-xyz" not in json.dumps(
        {key: value for key, value in refused.items() if key != "query_id"}
    )


def test_review_page_shows_unknowns_and_recommendations_without_a_submit_path(tmp_path):
    queue = ReviewQueue(tmp_path)
    _, run = _research("pod_research_ready", queue)
    assert run.stop_reason == "human_review"
    item = queue.get(run.review_item_id)
    assert item["status"] == "pending"
    assert item["unknowns"]
    assert any(rec["agent_id"] == "pod_product_draft_agent" for rec in item["recommendations"])
    page = render_reviews(queue)
    assert "TEST/MOCK" in page
    assert "Seasonality was not supplied." in page
    assert "pod_product_draft_agent" in page
    assert "publish_status=not_published" in page
    assert "<form" not in page.lower()
    assert "READ ONLY" in page

    injected = dict(item)
    injected["review_id"] = "rev-scriptcheck"
    injected["objective"] = "<script>alert(1)</script>"
    queue.enqueue(injected)
    escaped = render_reviews(queue)
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped


def test_review_server_is_get_only(tmp_path):
    queue = ReviewQueue(tmp_path)
    _research("pod_research_ready", queue)
    server = serve_reviews(queue, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "TEST/MOCK" in body
        assert "READ ONLY" in body
        connection.request("POST", "/", body="decision=approved")
        posted = connection.getresponse()
        posted.read()
        assert posted.status == 405
    finally:
        server.shutdown()
        server.server_close()
        connection.close()


def test_denied_review_does_not_launch_and_unresolved_ip_blocks_approval(tmp_path):
    queue = ReviewQueue(tmp_path)
    runner, run = _research("pod_research_ready", queue)
    denied = runner.apply_review_decision(run, queue, run.review_item_id, "denied", note="stop")
    assert denied["status"] == "denied"
    assert denied["decision"]["executed_external_action"] is False
    assert denied["consequential_actions_performed"] == []
    blocked = runner.attempt_action(run, "launch_store")
    assert blocked["executed"] is False
    assert any(reason["code"] == "phase_2_offline_no_consequential_actions" for reason in blocked["reasons"])
    assert run.audit.of_type("review_decision")
    assert run.audit.of_type("review_enqueued")

    from grokbot.fixtures.loader import load_fixture

    ip_runner = build_runner()
    fixture = load_fixture("attractive_economics_ip_risk")
    ip_run = ip_runner.open_opportunity(fixture["objective"], workflow_id=fixture["workflow_id"], fixture=fixture)
    ip_runner.run(ip_run, review_queue=queue)
    approved = ip_runner.apply_review_decision(ip_run, queue, ip_run.review_item_id, "approved", note="try")
    assert approved["status"] == "pending"
    assert approved["decision"]["decision"] == "blocked"
    assert approved["decision"]["blocked_reason"] == "unresolved_ip_risk"
    assert approved["decision"]["executed_external_action"] is False
    assert ip_run.external_actions_performed == []


def test_pod_research_stops_for_review_with_unpublished_drafts(tmp_path):
    _, run = _research("pod_research_ready", ReviewQueue(tmp_path))
    assert run.stop_reason == "human_review"
    assert run.project.status == "awaiting_approval"
    draft = run.outputs["pod_draft"]
    assert draft["store_launched"] is False
    assert draft["catalog_written"] is False
    assert draft["publish_status"] == "not_published"
    assert draft["production_connected"] is False
    assert {item["product_kind"] for item in draft["drafts"]} == {"shirt", "hat"}
    assert run.external_actions_performed == []
    assert run.outputs["market_research"]["network_calls"] == 0
    assert run.outputs["market_research"]["credentials_used"] is False


def test_incomplete_pod_research_requests_more_research():
    _, run = _research("pod_research_incomplete")
    assert run.stop_reason == "request_more_research"
    assert run.outputs["product_validation"]["validation_outcome"] == "RESEARCH_FURTHER"
    assert "pod_draft" not in run.outputs
    assert run.external_actions_performed == []


def test_dropship_ready_uses_mock_us_warehouse_without_a_commitment(tmp_path):
    _, run = _research("dropship_research_ready", ReviewQueue(tmp_path))
    assert run.stop_reason == "human_review"
    supplier = run.outputs["supplier_evidence"]
    assert supplier["us_fulfillment_evidence_status"] == "verified"
    assert supplier["commitment_made"] is False
    assert supplier["external_contact_made"] is False
    assert supplier["candidate_suppliers"][0]["display_name"] == "MOCK Warehouse Alpha"
    listing = run.outputs["listing_draft"]
    assert listing["listing_published"] is False
    assert listing["supplier_contacted"] is False
    assert listing["commitment_made"] is False
    assert listing["shipping_claim"]["epistemic_status"] != "FACT"
    assert "not a FACT" in listing["shipping_claim"]["statement"]
    assert run.external_actions_performed == []


def test_missing_us_warehouse_fails_the_supplier_gate():
    _, run = _research("dropship_missing_warehouse")
    assert run.stop_reason == "request_more_research"
    assert any(
        reason["code"] == "us_fulfillment_evidence_missing"
        for gate in run.gate_results
        for reason in gate["reasons"]
    )
    assert run.outputs["supplier_evidence"]["commitment_made"] is False
    assert run.outputs["supplier_evidence"]["external_contact_made"] is False
    assert "listing_draft" not in run.outputs
    unknown = build_listing_draft({}, {"us_fulfillment_evidence_status": "unknown", "epistemic_status": "UNKNOWN"})
    assert unknown["shipping_claim"]["epistemic_status"] == "UNKNOWN"
    assert "not claimed" in unknown["shipping_claim"]["statement"]


def test_fiverr_revision_draft_is_not_sent(tmp_path):
    _, run = _research("fiverr_revision_ready", ReviewQueue(tmp_path))
    assert run.stop_reason == "human_review"
    research = run.outputs["service_research"]
    draft = run.outputs["communication_draft"]
    workflow = run.outputs["service_workflow"]
    assert research["offer_known"] is True
    assert research["message_sent"] is False
    assert research["refund_issued"] is False
    assert research["order_placed"] is False
    assert draft["message_sent"] is False
    assert draft["refund_issued"] is False
    assert draft["requires_human_approval_to_send"] is True
    assert "not sent" in draft["draft"]["statement"].lower()
    assert workflow["project_state"] == "prepared_not_delivered"
    assert workflow["tasks"][2]["status"] == "not_sent"
    assert run.external_actions_performed == []


def test_fiverr_complaint_escalates_without_a_refund_or_message():
    runner, run = _research("fiverr_complaint_refund")
    assert run.stop_reason == "escalate"
    assert run.outputs["service_research"]["requests_refund"] is True
    assert run.outputs["service_research"]["refund_issued"] is False
    assert run.outputs["communication_draft"]["message_sent"] is False
    assert run.outputs["communication_draft"]["refund_issued"] is False
    assert run.outputs["communication_draft"]["recommended_disposition"] == "escalate_to_human"
    assert "compile_dossier" not in run.outputs
    for category in ("place_fiverr_order", "contact_fiverr_user", "customer_refund", "send_customer_message"):
        blocked = runner.attempt_action(run, category)
        assert blocked["executed"] is False
        assert any(reason["code"] == "phase_2_offline_no_consequential_actions" for reason in blocked["reasons"])
    assert run.external_actions_performed == []


def test_service_gate_fails_closed_and_does_not_apply_to_other_divisions():
    config = load_validation_gates()
    sent = evaluate_gate(
        "service_delivery_readiness",
        {
            "division": "digital_services",
            "service": {"offer_known": True, "message_sent": True},
            "communication": {"message_sent": False, "refund_issued": False},
            "service_workflow": {},
        },
        config,
    )
    assert sent["passed"] is False
    assert sent["reasons"][0]["code"] == "consequential_service_action_recorded"
    assert select_on_fail("request_more_research", [sent], None) == "halt"
    other = evaluate_gate(
        "service_delivery_readiness",
        {"division": "print_on_demand", "service": {}, "communication": {}, "service_workflow": {}},
        config,
    )
    assert other["passed"] is True
    assert other["applicable"] is False


def test_discovery_workflows_and_validate_command_still_pass():
    runner = build_runner()
    assert runner.identify_workflow(division="print_on_demand").id == "pod_opportunity_discovery"
    assert runner.identify_workflow(division="us_dropshipping").id == "us_dropshipping_opportunity_discovery"
    assert main(["validate"]) == 0
    context = build_gate_context(type("Run", (), {"outputs": {}, "workflow": type("W", (), {"division": "shared"})(), "gate_config": load_validation_gates()})())
    assert context["service"] == {}
