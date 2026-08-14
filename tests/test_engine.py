from unittest.mock import patch

import pytest

from src.engine import PolicyEngine
from src.models import Action, Permission, PolicySet, Prohibition, load_policy
from src.obligations import ObligationManager


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


def test_register_obligations_attributes_permission_id():

	engine = PolicyEngine(load_policy("policies/p2_obligation.yaml"))
	manager = ObligationManager()

	action = Action(
		subject="agent_1",
		action_type="install_software",
		resource="host://prod-01",
		context={"is_managed_host": True},
	)
	verdict = engine.evaluate(action)

	assert verdict.decision == "PERMIT"
	assert verdict.permission_ids == ["Perm_InstallSoftware"]
	assert "Ob_NotifyCISO" in verdict.obligations

	records = engine.register_obligations(manager, verdict=verdict, subject="agent_1")

	assert len(records) == 1
	assert records[0].obligation_id == "Ob_NotifyCISO"
	assert records[0].permission_id == "Perm_InstallSoftware"


def test_explicit_permit_explicit_prohibit_default_permit():

	policy = PolicySet(
		permissions=[],
		prohibitions=[],
		obligations=[],
		dispensations=[],
		rule_priorities=[],
		default_behavior="explicit_permit_explicit_prohibit",
		default_decision="PERMIT",
	)
	engine = PolicyEngine(policy)

	action = Action(subject="agent_1", action_type="anything", resource="r", context={})
	verdict = engine.evaluate(action)

	assert verdict.decision == "PERMIT"


def test_explicit_permit_explicit_prohibit_default_prohibit():

	policy = PolicySet(
		permissions=[],
		prohibitions=[],
		obligations=[],
		dispensations=[],
		rule_priorities=[],
		default_behavior="explicit_permit_explicit_prohibit",
		default_decision="PROHIBIT",
	)
	engine = PolicyEngine(policy)

	action = Action(subject="agent_1", action_type="anything", resource="r", context={})
	verdict = engine.evaluate(action)

	assert verdict.decision == "PROHIBIT"


def test_implicit_prohibit_overrides_default_permit():

	# In explicit_permit_implicit_prohibit, no-match is deny even if a default
	# decision is configured, because prohibition is implicit.
	policy = PolicySet(
		permissions=[],
		prohibitions=[],
		obligations=[],
		dispensations=[],
		rule_priorities=[],
		default_behavior="explicit_permit_implicit_prohibit",
		default_decision="PERMIT",
	)
	engine = PolicyEngine(policy)

	action = Action(subject="agent_1", action_type="anything", resource="r", context={})
	verdict = engine.evaluate(action)

	assert verdict.decision == "DEFAULT_DENY"






# ---- Issue #15: extended constraint matching ----

def _engine_with(permissions, prohibitions=(), default="explicit_permit_implicit_prohibit"):
	policy = PolicySet(
		permissions=list(permissions),
		prohibitions=list(prohibitions),
		obligations=[],
		default_behavior=default,
	)
	return PolicyEngine(policy)


def _eval_policy(policy, subject="agent_1", action_type="pay", resource="transaction://hvc",
				 context=None):
	engine = _engine_with(policy)
	verdict = engine.evaluate(Action(
		subject=subject, action_type=action_type, resource=resource, context=context or {},
	))
	return verdict.decision


def test_range_operator_gt():
	perm = Permission(id="Perm", action="pay", constraint={"amount": {"gt": 10000}})
	assert _eval_policy([perm], context={"amount": 50000}) == "PERMIT"
	assert _eval_policy([perm], context={"amount": 1000}) == "DEFAULT_DENY"


def test_range_operators_gte_and_lte():
	perm = Permission(id="Perm", action="pay", constraint={"amount": {"gte": 0, "lte": 1000}})
	assert _eval_policy([perm], context={"amount": 1000}) == "PERMIT"
	assert _eval_policy([perm], context={"amount": 500}) == "PERMIT"
	assert _eval_policy([perm], context={"amount": 1001}) == "DEFAULT_DENY"


def test_neq_operator():
	perm = Permission(id="Perm", action="pay", constraint={"region": {"neq": "restricted"}})
	assert _eval_policy([perm], context={"region": "eu"}) == "PERMIT"
	assert _eval_policy([perm], context={"region": "restricted"}) == "DEFAULT_DENY"


def test_in_operator():
	perm = Permission(id="Perm", action="pay", constraint={"role": {"in": ["ops", "finance"]}})
	assert _eval_policy([perm], context={"role": "ops"}) == "PERMIT"
	assert _eval_policy([perm], context={"role": "audit"}) == "DEFAULT_DENY"


def test_contains_operator():
	perm = Permission(id="Perm", action="pay", constraint={"tags": {"contains": ["high"]}})
	assert _eval_policy([perm], context={"tags": ["high", "priority"]}) == "PERMIT"
	assert _eval_policy([perm], context={"tags": ["low"]}) == "DEFAULT_DENY"


def test_wildcard_value():
	perm = Permission(id="Perm", action="read", constraint={"doc": "report-*"})
	assert _eval_policy([perm], action_type="read", resource="r", context={"doc": "report-2026"}) == "PERMIT"
	assert _eval_policy([perm], action_type="read", resource="r", context={"doc": "draft-1"}) == "DEFAULT_DENY"


def test_resource_pattern_wildcard():
	perm = Permission(id="Perm", action="read", constraint={"resource": "transaction://*"})
	assert _eval_policy([perm], action_type="read", resource="transaction://hvc-001") == "PERMIT"
	assert _eval_policy([perm], action_type="read", resource="file://local") == "DEFAULT_DENY"


def test_subject_scoping():
	perm = Permission(id="Perm", action="pay", constraint={"subject": "payments_agent_1"})
	assert _eval_policy([perm], subject="payments_agent_1") == "PERMIT"
	assert _eval_policy([perm], subject="other_agent") == "DEFAULT_DENY"


def test_explicit_operator_dict_backward_compat_still_matches_plain():
	# a permission using plain equality for a truthy key still works
	perm = Permission(id="Perm", action="pay", constraint={"is_high_value": True})
	assert _eval_policy([perm], context={"is_high_value": True}) == "PERMIT"
	assert _eval_policy([perm], context={"is_high_value": False}) == "DEFAULT_DENY"
