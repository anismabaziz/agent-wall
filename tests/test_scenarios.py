import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from src.engine import PolicyEngine
from src.models import Action, ObligationStatus, load_policy
from src.obligations import ObligationManager

SCENARIO_DIR = Path(__file__).parent.parent / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.json"))

@pytest.mark.parametrize("scenario_path", SCENARIO_FILES)
def test_scenarios(scenario_path):
	with open(scenario_path) as f:
		scenario = json.load(f)

	
	# init policy and engine
	policy_path = scenario.get("policy", "policies/p1_basic.yaml")
	policy = load_policy(policy_path)
	engine = PolicyEngine(policy)

	# init manager
	manager = ObligationManager(poll_interval_seconds=1)
	created_records = []

	last_verdict = None

	for action_data in scenario["actions"]:
		action = Action(**action_data)
		last_verdict = engine.evaluate(action)

		# register obligations from permitted actions
		if last_verdict.decision == "PERMIT" and last_verdict.obligations:
			created_records.extend(
				engine.register_obligations(
					manager,
					verdict=last_verdict,
					subject=action.subject,
				)
			)

		# check if this action fulfills any obligation
		manager.check_fulfillment(action)

		# check if action triggers any dispensations
		if policy.dispensations:
			manager.check_dispensation(action, policy.dispensations)


	# time advance for violated tests
	if "time_advance_minutes" in scenario:
		with freeze_time(datetime.now(timezone.utc) + timedelta(minutes=scenario["time_advance_minutes"])):
			manager._check_deadlines()


	# assert verdict for simple scenarios
	if "expected_decision" in scenario:
		assert last_verdict.decision == scenario["expected_decision"], \
			f"Scenario '{scenario["name"]}': expected {scenario["expected_decision"]}, got {last_verdict.decision}"
		
		if "expected_explanation_contains" in scenario:
			assert scenario["expected_explanation_contains"] in last_verdict.explanation, \
			f"Scenario '{scenario["name"]}': explanation {last_verdict.explanation}, missing {scenario["expected_explanation_contains"]}"

	# assert obligation status
	if "expected_final_obligation_status" in scenario:
		expected = getattr(ObligationStatus, scenario["expected_final_obligation_status"])
		assert created_records, f"Scenario '{scenario["name"]}': no obligations were created"

		last_record = created_records[-1]
		assert last_record.status == expected, \
		f"Scenario '{scenario["name"]}': expected {expected.value}, got {last_record.status}" 
