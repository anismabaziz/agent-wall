from datetime import datetime, timedelta, timezone
from freezegun import freeze_time
from src.models import Action, load_policy, PolicySet, Permission, Obligation, Dispensation
from src.engine import PolicyEngine
from src.obligations import ObligationManager, ObligationStatus


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