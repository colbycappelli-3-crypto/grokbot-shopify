import pytest

from grokbot.agents.registry import AgentRegistry, AgentSpec, DuplicateAgentError
from grokbot.policy.approval import ActionClass


def _spec(agent_id="a", division="shared"):
    return AgentSpec(
        id=agent_id,
        name="Agent",
        version="0.1.0",
        role="Role",
        division=division,
        status="draft",
        description="desc",
        default_permission=ActionClass.AUTONOMOUS,
    )


def test_add_and_get():
    registry = AgentRegistry([_spec("alpha")])
    assert "alpha" in registry
    assert registry.get("alpha").id == "alpha"
    assert len(registry) == 1


def test_duplicate_ids_rejected():
    with pytest.raises(DuplicateAgentError):
        AgentRegistry([_spec("dup"), _spec("dup")])


def test_by_division():
    registry = AgentRegistry([_spec("a", "shared"), _spec("b", "us_dropshipping")])
    assert {s.id for s in registry.by_division("shared")} == {"a"}
    assert {s.id for s in registry.by_division("us_dropshipping")} == {"b"}


def test_loaded_registry_has_expected_core_agents():
    registry = AgentRegistry.load()
    for expected in ("market_research_agent", "shopify_store_builder_agent"):
        assert expected in registry
