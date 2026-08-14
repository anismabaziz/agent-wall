from datetime import datetime, timedelta, timezone
from freezegun import freeze_time
from src.models import Action, load_policy, PolicySet, Permission, Obligation, Dispensation, ObligationStatus
from src.engine import PolicyEngine
from src.obligations import ObligationManager


def test_obligation_violated_after_deadline():

	policy = load_policy("policies/p2_obligation.yaml")
	engine = PolicyEngine(policy)
	manager = ObligationManager(poll_interval_seconds=1)

	action1 = Action(
		subject="agent_1",
		action_type="install_software",
		resource="host://prod-01",
		context={
			"is_managed_host": True
		}
	)
	verdict = engine.evaluate(action1)
	assert verdict.decision == "PERMIT"
	assert "Ob_NotifyCISO" in verdict.obligations

	manager.register(
		obligation_id="Ob_NotifyCISO",
		permission_id="Perm_InstallSoftware",
		subject="agent_1",
		obliged_action="notify_ciso",
		deadline_minutes=60
	)

	with freeze_time(datetime.now(timezone.utc) + timedelta(minutes=61)):
		manager._check_deadlines()

	pending = manager.get_obligations(ObligationStatus.PENDING)
	violated = manager.get_obligations(ObligationStatus.VIOLATED)

	assert len(pending) == 0
	assert len(violated) == 1
	assert violated[0].obligation_id == "Ob_NotifyCISO"


def test_obligation_fulfilled_before_deadline():

	policy = load_policy("policies/p2_obligation.yaml")
	engine = PolicyEngine(policy)
	manager = ObligationManager(poll_interval_seconds=1)

	action1 = Action(
		subject="agent_1",
		action_type="install_software",
		resource="host://prod-01",
		context={
			"is_managed_host": True
		}
	)
	verdict = engine.evaluate(action1)
	assert verdict.decision == "PERMIT"
	assert "Ob_NotifyCISO" in verdict.obligations

	manager.register(
		obligation_id="Ob_NotifyCISO",
		permission_id="Perm_InstallSoftware",
		subject="agent_1",
		obliged_action="notify_ciso",
		deadline_minutes=60
	)

	action2 = Action(
		subject="agent_1",
		action_type="notify_ciso",
		resource="ciso@company.com",
		context={}
	)

	fulfilled = manager.check_fulfillment(action2)

	assert fulfilled is not None
	assert fulfilled.status == ObligationStatus.FULFILLED

	with freeze_time(datetime.now(timezone.utc) + timedelta(minutes=61)):
		manager._check_deadlines()

	fulfilled_records = manager.get_obligations(ObligationStatus.FULFILLED)

	assert len(fulfilled_records) == 1


def test_shared_obligation_fulfilled_once():
	"""
	Two permissions provision same obligation; one fulfillment closes both.
	"""

	policy = PolicySet(
    permissions=[
      Permission(id="Perm_A", action="install", constraint={}, provisions=["Ob_Log"]),
      Permission(id="Perm_B", action="install", constraint={}, provisions=["Ob_Log"]),
    ],
    obligations=[Obligation(id="Ob_Log", obliged_action="log_access", deadline_minutes=60, description="Log it")],
		default_behavior="explicit_permit_implicit_prohibit"
  )
	engine = PolicyEngine(policy)
	manager = ObligationManager()

	action = Action(
		subject="agent_1",
		action_type="install",
		resource="host",
		context={}
	)
	verdict = engine.evaluate(action)
	assert len(verdict.obligations) == 1

	obligation = policy.obligations[0]
	manager.register(
		obligation_id=obligation.id,
		permission_id="Perm_A",
		subject="agent_1",
		obliged_action=obligation.obliged_action,
		deadline_minutes=obligation.deadline_minutes
	)

	pending = manager.get_obligations(ObligationStatus.PENDING)
	assert len(pending) == 1
	assert pending[0].obligation_id == "Ob_Log"

	fulfill_action = Action(
		subject="agent_1",
		action_type="log_access",
		resource="host",
		context={}
	)
	manager.check_fulfillment(fulfill_action)

	fulfilled = manager.get_obligations(ObligationStatus.FULFILLED)
	assert len(fulfilled) == 1



def test_late_dispensation_not_applied():
	"""
	Dispensation arriving after VIOLATED don't change state.
	"""

	policy = load_policy("policies/p2_obligation.yaml")
	engine = PolicyEngine(policy)
	manager = ObligationManager()

	action1 = Action(
		subject="agent_1",
		action_type="install_software",
		resource="host://prod-01",
		context={
			"is_managed_host": True
		}
	)
	verdict = engine.evaluate(action1)

	record = manager.register(
		obligation_id="Ob_NotifyCISO",
		permission_id="Perm_InstallSoftware",
		subject="agent_1",
		obliged_action="notify_ciso",
		deadline_minutes=60
	)

	with freeze_time(datetime.now(timezone.utc) + timedelta(minutes=61)):
		manager._check_deadlines()

	assert record.status == ObligationStatus.VIOLATED

	disp_action = Action(
		subject="agent_1",
		action_type="some_action",
		resource="exempt_party",
		context={
			"is_exempt": True
		}
	)

	dispensation = Dispensation(
		id="Disp_Late",
		constraint={
			"is_exempt": True
		},
		waives="Ob_NotifyCISO"
	)
	result = manager.check_dispensation(disp_action, [dispensation])

	assert record.status == ObligationStatus.VIOLATED
	assert result is None


def test_dispensation_waives_pending_obligation():
	"""
	Dispensation arriving while PENDING => WAIVED.
	"""
	
	manager = ObligationManager()

	record = manager.register(
			obligation_id="Ob_NotifyCISO",
			permission_id="Perm_InstallSoftware",
			subject="agent_1",
			obliged_action="notify_ciso",
			deadline_minutes=60
	)
	assert record.status == ObligationStatus.PENDING

	disp_action = Action(
			subject="agent_1",
			action_type="check_exemption",
			resource="exempt_party",
			context={"is_exempt_counterparty": True}
	)
	dispensation = Dispensation(
			id="Disp_ExemptCISO",
			constraint={"is_exempt_counterparty": True},
			waives="Ob_NotifyCISO"
	)
	result = manager.check_dispensation(disp_action, [dispensation])

	assert result is not None
	assert result.status == ObligationStatus.WAIVED
	assert result.waived_by == "Disp_ExemptCISO"


def test_dispensation_wrong_constraint_no_waive():
	"""
	Dispensation constraint doesn't match action context => no waiver.
	"""

	manager = ObligationManager()

	record = manager.register(
			obligation_id="Ob_NotifyCISO",
			permission_id="Perm_Install",
			subject="agent_1",
			obliged_action="notify_ciso",
			deadline_minutes=60
	)

	disp_action = Action(
			subject="agent_1",
			action_type="check_exemption",
			resource="party",
			context={"is_exempt_counterparty": False}  # WRONG: False, not True
	)
	dispensation = Dispensation(
			id="Disp_Exempt",
			constraint={"is_exempt_counterparty": True},  # expects True
			waives="Ob_NotifyCISO"
	)
	result = manager.check_dispensation(disp_action, [dispensation])

	assert result is None
	assert record.status == ObligationStatus.PENDING


def test_fulfillment_matches_correct_obligation():
	"""
	Two pending obligations, fulfillment only closes the matching one.
	"""

	manager = ObligationManager()

	manager.register(
			obligation_id="Ob_NotifyCISO",
			permission_id="Perm_Install",
			subject="agent_1",
			obliged_action="notify_ciso",
			deadline_minutes=60
	)
	manager.register(
			obligation_id="Ob_LogAccess",
			permission_id="Perm_Read",
			subject="agent_1",
			obliged_action="log_access",
			deadline_minutes=30
	)

	pending = manager.get_obligations(ObligationStatus.PENDING)
	assert len(pending) == 2

	action = Action(
			subject="agent_1",
			action_type="log_access",  # matches Ob_LogAccess, not Ob_NotifyCISO
			resource="audit",
			context={}
	)
	result = manager.check_fulfillment(action)

	assert result is not None
	assert result.obligation_id == "Ob_LogAccess"

	pending = manager.get_obligations(ObligationStatus.PENDING)
	assert len(pending) == 1
	assert pending[0].obligation_id == "Ob_NotifyCISO"

	fulfilled = manager.get_obligations(ObligationStatus.FULFILLED)
	assert len(fulfilled) == 1


def test_fulfillment_requires_matching_constraint():
	"""
	An action can only fulfill an obligation if its context satisfies the
	obligation's fulfillment_constraint.
	"""
	manager = ObligationManager()

	manager.register(
		obligation_id="Ob_FileCTR",
		permission_id="Perm_ApprovedHighValue",
		subject="agent_1",
		obliged_action="file_ctr",
		deadline_minutes=60,
		fulfillment_constraint={"requires_note": True},
	)

	missing = manager.check_fulfillment(
		Action(subject="agent_1", action_type="file_ctr", resource="ctr/1", context={})
	)
	assert missing is None

	matching = manager.check_fulfillment(
		Action(subject="agent_1", action_type="file_ctr", resource="ctr/1", context={"requires_note": True})
	)
	assert matching is not None
	assert matching.status == ObligationStatus.FULFILLED

# ---- Issue #16: deterministic dispensation -> fulfillment -> deadline ordering ----

def test_enforce_applies_dispensation_before_fulfillment():
	"""When a dispensation and a fulfillment match the same action, waiver wins."""
	manager = ObligationManager()
	manager.register(
		obligation_id="Ob_FileCTR",
		permission_id="Perm_HighValue",
		subject="agent_1",
		obliged_action="file_ctr",
		deadline_minutes=60,
	)

	dispensation = Dispensation(
		id="Disp_ExemptCTR",
		constraint={"is_exempt_counterparty": True},
		waives="Ob_FileCTR",
	)

	action = Action(
		subject="agent_1",
		action_type="file_ctr",
		resource="ctr/1",
		context={"is_exempt_counterparty": True},
	)

	outcomes = manager.enforce(action, [dispensation], check_deadline=False)

	assert len(outcomes["dispensation"]) == 1
	assert outcomes["dispensation"][0].status == ObligationStatus.WAIVED

	# fulfillment runs after dispensation, so nothing left PENDING to fulfill
	oblig = next(o for o in manager.get_obligations() if o.obligation_id == "Ob_FileCTR")
	assert oblig.status == ObligationStatus.WAIVED


def test_enforce_fulfills_when_no_dispensation_matches():
	manager = ObligationManager()
	manager.register(
		obligation_id="Ob_FileCTR",
		permission_id="Perm_HighValue",
		subject="agent_1",
		obliged_action="file_ctr",
		deadline_minutes=60,
	)
	action = Action(subject="agent_1", action_type="file_ctr", resource="ctr/1", context={})

	outcomes = manager.enforce(action, [Dispensation(id="d", constraint={"nope": True}, waives="Ob_FileCTR")],
							   check_deadline=False)
	assert outcomes["dispensation"] == []
	assert outcomes["fulfilled"] is not None
	assert outcomes["fulfilled"].status == ObligationStatus.FULFILLED


def test_enforce_marks_past_deadline_as_violated():
	manager = ObligationManager()
	record = manager.register(
		obligation_id="Ob_FileCTR",
		permission_id="Perm_HighValue",
		subject="agent_1",
		obliged_action="file_ctr",
		deadline_minutes=60,
	)

	action = Action(subject="agent_1", action_type="something_else", resource="r", context={})
	with freeze_time(datetime.now(timezone.utc) + timedelta(minutes=61)):
		manager.enforce(action, [], check_deadline=True)

	assert record.status == ObligationStatus.VIOLATED
