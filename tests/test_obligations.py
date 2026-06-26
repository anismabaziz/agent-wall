import pytest
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time
from src.models import Action, load_policy
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