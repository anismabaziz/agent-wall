import json
import pytest
from pathlib import Path

from obligo.models import PolicySet, Action, load_policy
from obligo.engine import PolicyEngine


SCENARIO_DIR = Path(__file__).parent.parent / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.json"))

@pytest.mark.parametrize("scenario_path", SCENARIO_FILES)
def test_scenarios(scenario_path):
	with open(scenario_path) as f:
		scenario = json.load(f)

	
	policy_path = scenario.get("policy", "policies/p1_basic.yaml")
	engine = PolicyEngine(load_policy(policy_path))

	action = Action(**scenario["action"])
	verdict = engine.evaluate(action)

	assert verdict.decision == scenario["expected_decision"], \
		f"Scenario '{scenario["name"]}': expected {scenario["expected_decision"]}, got {verdict.decision}"
	
	if "expected_explanation_contains" in scenario:
		assert scenario["expected_explanation_contains"] in verdict.explanation, \
		f"Scenario '{scenario["name"]}': explanation {verdict.explanation}, missing {scenario["expected_explanation_contains"]}"
