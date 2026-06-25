import pytest
from obligo.models import Action, load_policy, PolicySet, Permission, Prohibition
from obligo.engine import PolicyEngine
from unittest.mock import patch


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


def test_unresolved_conflict_defaults_to_deny():
	policy = PolicySet(
		permissions=[
			Permission(id="Perm_All", action="read_file", constraint={})
		],
		prohibitions=[
			Prohibition(id="Proh_All", action="read_file", constraint={})
		],
		obligations=[], dispensations=[], rule_priorities=[],
		default_behavior="explicit_permit_implicit_prohibit"
	)

	engine = PolicyEngine(policy)

	action = Action(
		subject="agent_1",
		action_type="read_file",
		resource="files/public/report.pdf",
		context={}
	)

	verdict = engine.evaluate(action)

	assert verdict.decision == "DEFAULT_DENY"
	assert "conflict" in verdict.explanation.lower()
	assert "Perm_All" in verdict.explanation
	assert "Proh_All" in verdict.explanation


def test_default_deny_when_nothing_matches(p1_engine):
	action = Action(
		subject="agent_1",
		action_type="execute_code",
		resource="script.py",
		context={"is_user_record": False}
	)

	verdict = p1_engine.evaluate(action)

	assert verdict.decision == "DEFAULT_DENY"


def test_evaluate_never_raises_uncaught_exception(p1_engine):
	action = Action(
		subject="agent_1",
		action_type="read_file",
		resource="files/public/report.pdf",
		context={"is_public": True}
	)

	with patch.object(p1_engine, '_evaluate', side_effect=RuntimeError("boom")):
		verdict = p1_engine.evaluate(action)
		assert verdict.decision == "DEFAULT_DENY"
		assert "boom" in verdict.explanation.lower()



def test_engine_uses_rulepriority_to_permit():

	engine = PolicyEngine(load_policy("policies/p3_conflict.yaml"))

	action = Action(
		subject="agent_1",
		action_type="export_dataset",
		resource="dataset://regulated",
		context={
			"is_regulated": True,
			"has_compliance_credential": True
		}
	)

	verdict = engine.evaluate(action)

	assert verdict.decision == "PERMIT"
	assert "PriorityApprovalOverProh" in verdict.explanation


def test_engine_unresolved_conflict_defaults_to_deny():

	engine = PolicyEngine(load_policy("policies/p4_tiebreak.yaml"))

	action = Action(
    subject="agent_1",
    action_type="export_dataset",
    resource="dataset://regulated",
    context={"is_regulated": True, "has_manager_approval": True}
  )

	verdict = engine.evaluate(action)

	assert verdict.decision == "DEFAULT_DENY"
	assert "Unresolved conflict" in verdict.explanation




