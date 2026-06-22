import pytest
from obligo.models import Action, load_policy
from obligo.engine import PolicyEngine


@pytest.fixture
def p1_engine():
	policy_set = load_policy("policies/p1_basic.yaml")
	return PolicyEngine(policy_set)


def test_permit_when_only_permission_matches(p1_engine):
	action = Action(
		subject="agent_1",
		action_type="read_file",
		resource="/docs/public/report.pdf",
		context={"is_public": True}
	)

	verdict = p1_engine.evaluate(action)

	assert verdict.decision == "PERMIT"
	assert "Perm_ReadPublicDoc" in verdict.explanation


def test_prohibit_when_only_prohibition_matches(p1_engine):
	action = Action(
		subject="agent_1",
		action_type="delete_user",
		resource="user://42",
		context={"is_user_record": True}
	)

	verdict = p1_engine.evaluate(action)

	assert verdict.decision == "PROHIBIT"
	assert "Proh_DeleteUser" in verdict.explanation


def test_default_deny_when_nothing_matches(p1_engine):
	action = Action(
		subject="agent_1",
		action_type="execute_code",
		resource="script.py",
		context={"is_user_record": False}
	)

	verdict = p1_engine.evaluate(action)

	assert verdict.decision == "DEFAULT_DENY"
