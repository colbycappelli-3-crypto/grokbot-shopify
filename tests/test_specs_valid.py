"""The shipped specs and configuration must load and validate cleanly."""
from grokbot.agents.registry import AgentRegistry
from grokbot.policy.approval import load_default_policy
from grokbot.workflows.loader import load_all_workflows


def test_all_agent_specs_load_and_validate():
    registry = AgentRegistry.load()
    assert len(registry) >= 1
    # ids are unique (load() would have raised otherwise) and well-formed
    for spec in registry.all():
        assert spec.id
        assert spec.default_permission.value in {
            "AUTONOMOUS",
            "APPROVAL_REQUIRED",
            "PROHIBITED",
        }


def test_all_workflows_load_and_are_acyclic():
    workflows = load_all_workflows()
    assert len(workflows) >= 1
    for workflow in workflows:
        order = workflow.execution_order()
        assert len(order) == len(workflow.stages)


def test_default_policy_loads():
    policy = load_default_policy()
    assert policy.version
    # fail-safe default must never be autonomous
    assert policy.default_class.value != "AUTONOMOUS"
    assert len(policy.categories()) >= 1


def test_every_workflow_agent_exists_in_registry():
    registry = AgentRegistry.load()
    for workflow in load_all_workflows():
        for stage in workflow.stages:
            if stage.agent is not None:
                assert stage.agent in registry, (
                    f"workflow '{workflow.id}' stage '{stage.id}' references "
                    f"unknown agent '{stage.agent}'"
                )
