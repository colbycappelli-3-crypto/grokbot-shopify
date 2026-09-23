from grokbot.agents.registry import AgentRegistry
from grokbot.orchestrator.orchestrator import Orchestrator
from grokbot.policy.approval import load_default_policy
from grokbot.workflows.loader import load_all_workflows


def _orchestrator():
    registry = AgentRegistry.load()
    policy = load_default_policy()
    workflows = load_all_workflows()
    return Orchestrator(registry, policy, workflows=workflows), workflows


def test_plan_orders_stages_topologically():
    orch, workflows = _orchestrator()
    plan = orch.plan("Find a winning product", "us_dropshipping_opportunity")
    ids = [t.stage_id for t in plan.tasks]
    assert ids.index("market_scan") < ids.index("demand_validation")
    assert ids.index("demand_gate") < ids.index("supplier_scan")
    assert ids.index("viability_gate") < ids.index("launch_approval") < ids.index("store_build")


def test_plan_flags_required_owner_approval():
    orch, _ = _orchestrator()
    plan = orch.plan("obj", "us_dropshipping_opportunity")
    assert plan.requires_owner_approval is True
    assert any(t.stage_type == "approval_gate" for t in plan.tasks)
    # the store build action is APPROVAL_REQUIRED
    build = next(t for t in plan.tasks if t.stage_id == "store_build")
    assert build.requires_approval is True
    assert build.action_class == "APPROVAL_REQUIRED"


def test_plan_resolves_agent_roles():
    orch, _ = _orchestrator()
    plan = orch.plan("obj", "pod_product_concept")
    niche = next(t for t in plan.tasks if t.stage_id == "niche_research")
    assert niche.agent_role == "Market Research Agent"
    assert not plan.warnings


def test_new_project_seeds_all_stages():
    orch, _ = _orchestrator()
    state = orch.new_project("proj-x", "Proj X", "pod_product_concept")
    assert state.data["division"] == "print_on_demand"
    assert {s["stage_id"] for s in state.data["stages"]} == {
        "niche_research",
        "ip_screen",
        "concept_gate",
        "store_setup_approval",
        "store_build",
    }
