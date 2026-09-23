import pytest

from grokbot.policy.approval import ActionClass, ApprovalPolicy, load_default_policy


def test_classify_known_categories():
    policy = load_default_policy()
    assert policy.classify("market_research").action_class is ActionClass.AUTONOMOUS
    assert policy.classify("launch_store").action_class is ActionClass.APPROVAL_REQUIRED
    assert policy.classify("expose_credentials").action_class is ActionClass.PROHIBITED


def test_unknown_category_uses_failsafe_default():
    policy = load_default_policy()
    decision = policy.classify("some_unlisted_action")
    assert decision.matched is False
    assert decision.action_class is ActionClass.APPROVAL_REQUIRED


def test_owner_can_override_non_prohibited():
    policy = load_default_policy()
    policy.set_override("market_research", ActionClass.APPROVAL_REQUIRED)
    assert policy.classify("market_research").action_class is ActionClass.APPROVAL_REQUIRED


def test_prohibited_cannot_be_relaxed():
    policy = load_default_policy()
    with pytest.raises(PermissionError):
        policy.set_override("expose_credentials", ActionClass.AUTONOMOUS)
    # still prohibited after the failed attempt
    assert policy.classify("expose_credentials").action_class is ActionClass.PROHIBITED


def test_locked_policy_rejects_overrides():
    policy = ApprovalPolicy(
        {
            "version": "1.0.0",
            "default_class": "APPROVAL_REQUIRED",
            "owner_can_override": False,
            "classes": {
                "AUTONOMOUS": {"description": "x"},
                "APPROVAL_REQUIRED": {"description": "x"},
                "PROHIBITED": {"description": "x"},
            },
            "rules": [{"category": "market_research", "class": "AUTONOMOUS"}],
        }
    )
    with pytest.raises(PermissionError):
        policy.set_override("market_research", ActionClass.APPROVAL_REQUIRED)
