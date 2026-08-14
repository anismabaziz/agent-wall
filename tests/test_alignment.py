"""Tests for the aligned pathway (type reasoning + credential gate)."""

from src.audit import _policy_hash_public
from src.engine import PolicyEngine
from src.models import Action, OntologyClass, Permission, PolicySet, load_policy


def _engine(permissions, prohibitions=(), ontology=(), authorities=()):
	return PolicyEngine(
		PolicySet(
			permissions=list(permissions),
			prohibitions=list(prohibitions),
			obligations=[],
			ontology=list(ontology),
			credential_authorities=list(authorities),
			default_behavior="explicit_permit_implicit_prohibit",
		)
	)

ONTOLOGY = [
	OntologyClass(id="Transaction", subClassOf=[]),
	OntologyClass(id="HighValueTransaction", subClassOf=["Transaction"]),
	OntologyClass(id="CrossBorderTransfer", subClassOf=["HighValueTransaction"]),
]


def test_matches_type_via_subclass_reasoning():
	perm = Permission(id="Perm", action="pay", constraint={"matches_type": "HighValueTransaction"})
	engine = _engine([perm], ontology=ONTOLOGY)
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={"_resource_types": ["CrossBorderTransfer"]})).decision == "PERMIT"
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={"_resource_types": ["LocalTransfer"]})).decision == "DEFAULT_DENY"


def test_future_subclass_is_auto_covered():
	# adding a subclass later requires no rule edit
	extended = ONTOLOGY + [OntologyClass(id="CryptoTransfer", subClassOf=["HighValueTransaction"])]
	perm = Permission(id="Perm", action="pay", constraint={"matches_type": "HighValueTransaction"})
	engine = _engine([perm], ontology=extended)
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={"_resource_types": ["CryptoTransfer"]})).decision == "PERMIT"


def test_matches_type_exact_without_ontology():
	perm = Permission(id="Perm", action="pay", constraint={"matches_type": "HighValueTransaction"})
	engine = _engine([perm])
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={"_resource_types": ["HighValueTransaction"]})).decision == "PERMIT"


def test_missing_type_denies():
	perm = Permission(id="Perm", action="pay", constraint={"matches_type": "HighValueTransaction"})
	engine = _engine([perm], ontology=ONTOLOGY)
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={})).decision == "DEFAULT_DENY"


def test_credential_accept_trusted_issuer():
	perm = Permission(id="Perm", action="pay", constraint={"credential": "TreasuryAuthority"})
	engine = _engine([perm], authorities=["TreasuryAuthority"])
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={"_credential_issuer": "TreasuryAuthority"})).decision == "PERMIT"


def test_credential_reject_untrusted_issuer():
	perm = Permission(id="Perm", action="pay", constraint={"credential": "TreasuryAuthority"})
	engine = _engine([perm], authorities=["TreasuryAuthority"])
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={"_credential_issuer": "Mallory"})).decision == "DEFAULT_DENY"


def test_credential_missing_denies():
	perm = Permission(id="Perm", action="pay", constraint={"credential": "TreasuryAuthority"})
	engine = _engine([perm], authorities=["TreasuryAuthority"])
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={})).decision == "DEFAULT_DENY"


def test_credential_true_accepts_any_trusted():
	perm = Permission(id="Perm", action="pay", constraint={"credential": True})
	engine = _engine([perm], authorities=["TreasuryAuthority", "ComplianceDesk"])
	assert engine.evaluate(Action(subject="a", action_type="pay", resource="r",
								  context={"_credential_issuer": "ComplianceDesk"})).decision == "PERMIT"


def test_constraint_match_reused_for_dispensations():
	engine = _engine([], ontology=ONTOLOGY)
	assert engine.constraint_match({"_resource_types": ["CrossBorderTransfer"]},
								   {"matches_type": "HighValueTransaction"}) is True
	assert engine.constraint_match({"_resource_types": ["LocalTransfer"]},
								   {"matches_type": "HighValueTransaction"}) is False


def test_flagship_policy_end_to_end():
	policy = load_policy("policies/p5_composite.yaml")
	engine = PolicyEngine(policy)

	approved = Action(subject="pay_agent", action_type="execute_payment", resource="tx://hvc",
					  context={"_resource_types": ["CrossBorderTransfer"],
							   "_credential_issuer": "TreasuryAuthority"})
	assert engine.evaluate(approved).decision == "PERMIT"

	no_cred = Action(subject="pay_agent", action_type="execute_payment", resource="tx://hvc",
					 context={"_resource_types": ["CrossBorderTransfer"]})
	assert engine.evaluate(no_cred).decision == "PROHIBIT"

	no_type = Action(subject="pay_agent", action_type="execute_payment", resource="tx://hvc",
					 context={})
	assert engine.evaluate(no_type).decision == "DEFAULT_DENY"


def test_policy_version_hash():
	h1 = _policy_hash_public("policies/p5_composite.yaml")
	h2 = _policy_hash_public("policies/p1_basic.yaml")
	assert len(h1) == 64
	assert h1 != h2


def test_policy_version_hash_empty_for_missing():
	assert _policy_hash_public("policies/does_not_exist.yaml") == ""