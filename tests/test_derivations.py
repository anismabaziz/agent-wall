"""Tests for src/derivations.py (issue #6)."""
from src.models import PolicySet, Permission, Obligation
from src.derivations import derived_obligations, deriving_permissions


def _policy():
	return PolicySet(
		permissions=[
			Permission(id="Perm_A", action="install", constraint={}, provisions=["Ob_Log"]),
			Permission(id="Perm_B", action="install", constraint={}, provisions=["Ob_Log"]),
			Permission(id="Perm_C", action="read", constraint={}, provisions=["Ob_Report"]),
			Permission(id="Perm_NoObligation", action="noop", constraint={}),
		],
		obligations=[
			Obligation(id="Ob_Log", obliged_action="log_access", deadline_minutes=60, description="Log"),
			Obligation(id="Ob_Report", obliged_action="submit_report", deadline_minutes=1440, description="Report"),
		],
		default_behavior="explicit_permit_implicit_prohibit",
	)


def test_shared_obligation_derived_once():
	obls = derived_obligations(_policy(), ["Perm_A", "Perm_B"])
	assert [o.id for o in obls] == ["Ob_Log"]


def test_derives_from_multiple_permissions_deduped():
	obls = derived_obligations(_policy(), ["Perm_A", "Perm_B", "Perm_C"])
	assert sorted(o.id for o in obls) == ["Ob_Log", "Ob_Report"]


def test_empty_when_no_permissions():

	assert derived_obligations(_policy(), []) == []


def test_ignores_permissions_not_in_policy():
	obls = derived_obligations(_policy(), ["Perm_DoesNotExist"])
	assert obls == []


def test_unknown_provisioned_id_skipped():
	policy = PolicySet(
		permissions=[Permission(id="Perm_A", action="a", constraint={}, provisions=["Ob_Ghost"])],
		obligations=[
			Obligation(id="Ob_Only", obliged_action="x", deadline_minutes=1, description="only"),
		],
		default_behavior="explicit_permit_implicit_prohibit",
	)
	assert derived_obligations(policy, ["Perm_A"]) == []


def test_deriving_permissions_provenance():
	perms = deriving_permissions(_policy(), "Ob_Log")
	assert sorted(p.id for p in perms) == ["Perm_A", "Perm_B"]