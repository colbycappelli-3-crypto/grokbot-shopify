import pytest

from grokbot.workflows.loader import WorkflowError, WorkflowSpec


def _wf(stages):
    return {
        "id": "wf",
        "name": "WF",
        "version": "0.1.0",
        "division": "shared",
        "description": "test",
        "stages": stages,
    }


def _action(sid, depends_on=None):
    return {
        "id": sid,
        "name": sid,
        "type": "action",
        "agent": "some_agent",
        "permission": "AUTONOMOUS",
        "depends_on": depends_on or [],
    }


def test_topological_order_respects_dependencies():
    wf = WorkflowSpec.from_dict(
        _wf([_action("a"), _action("b", ["a"]), _action("c", ["b"])])
    )
    order = wf.execution_order()
    assert order.index("a") < order.index("b") < order.index("c")


def test_branching_order():
    wf = WorkflowSpec.from_dict(
        _wf(
            [
                _action("root"),
                _action("left", ["root"]),
                _action("right", ["root"]),
                _action("join", ["left", "right"]),
            ]
        )
    )
    order = wf.execution_order()
    assert order[0] == "root"
    assert order.index("join") > order.index("left")
    assert order.index("join") > order.index("right")


def test_cycle_detected():
    with pytest.raises(WorkflowError, match="cycle"):
        WorkflowSpec.from_dict(_wf([_action("a", ["b"]), _action("b", ["a"])]))


def test_unknown_dependency_rejected():
    with pytest.raises(WorkflowError, match="unknown stage"):
        WorkflowSpec.from_dict(_wf([_action("a", ["missing"])]))


def test_self_dependency_rejected():
    with pytest.raises(WorkflowError, match="itself"):
        WorkflowSpec.from_dict(_wf([_action("a", ["a"])]))


def test_gates_detected():
    wf = WorkflowSpec.from_dict(
        _wf(
            [
                _action("a"),
                {
                    "id": "gate",
                    "name": "Gate",
                    "type": "validation_gate",
                    "depends_on": ["a"],
                    "validation": {"criteria": ["ok"], "on_fail": "halt"},
                },
            ]
        )
    )
    assert [g.id for g in wf.gates()] == ["gate"]
