import pytest

from grokbot.policy.approval import ActionClass
from grokbot.state.project_state import ProjectState
from grokbot.validation import SpecValidationError


def _new():
    return ProjectState.new(
        project_id="proj-1",
        name="Test Project",
        division="us_dropshipping",
        workflow_id="us_dropshipping_opportunity",
        stages=["market_scan", "demand_gate"],
    )


def test_new_project_is_valid_and_pending():
    state = _new()
    assert state.status == "proposed"
    assert state.stage("market_scan")["status"] == "pending"


def test_evidence_defaults_to_unknown():
    state = _new()
    item = state.record_evidence("competitor_count")
    assert item["status"] == "UNKNOWN"
    assert "value" not in item


def test_evidence_verified_requires_source():
    state = _new()
    with pytest.raises(ValueError):
        state.record_evidence("price", value=19.99, verified=True)
    item = state.record_evidence("price", value=19.99, sources=["https://example/src"], verified=True)
    assert item["status"] == "verified"
    assert item["sources"] == ["https://example/src"]


def test_unverified_evidence_without_source():
    state = _new()
    item = state.record_evidence("demand", value="high")
    assert item["status"] == "unverified"


def test_decisions_and_approvals_are_audited():
    state = _new()
    state.add_decision(actor="grokbot", summary="Proceed to supplier research", rationale="demand gate passed")
    state.request_approval("launch_store", ActionClass.APPROVAL_REQUIRED)
    state.escalate("Refund request from customer")
    assert len(state.data["decisions"]) == 1
    assert state.data["approvals"][0]["status"] == "pending"
    assert state.data["escalations"][0]["status"] == "open"


def test_update_stage_and_status():
    state = _new()
    state.update_stage("market_scan", "in_progress")
    state.update_stage("market_scan", "passed", notes="done")
    state.set_status("researching")
    assert state.stage("market_scan")["status"] == "passed"
    assert state.status == "researching"


def test_roundtrip_json_and_yaml(tmp_path):
    state = _new()
    state.record_evidence("x", value=1, sources=["s"], verified=True)
    for suffix in (".json", ".yaml"):
        path = tmp_path / f"state{suffix}"
        state.save(path)
        reloaded = ProjectState.load(path)
        assert reloaded.project_id == state.project_id
        assert reloaded.data["evidence"]["x"]["status"] == "verified"


def test_invalid_state_rejected():
    with pytest.raises(SpecValidationError):
        ProjectState({"project_id": "x", "name": "n"})  # missing required fields
