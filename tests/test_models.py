import pytest
from pydantic import ValidationError

from src.models import PolicySet, load_policy


def test_load_valid_policy():
	policy_set = load_policy("policies/p1_basic.yaml")

	assert isinstance(policy_set, PolicySet)
	assert policy_set.default_behavior == "explicit_permit_implicit_prohibit"


def test_empty_yaml_file(tmp_path):
	file = tmp_path / "empty.yaml"
	file.write_text("")

	print("RAW:", repr(file.read_text())) 

	with pytest.raises(ValueError):
		load_policy(file)


def test_invalid_yaml_schema(tmp_path):
	file = tmp_path / "invalid.yaml"
	file.write_text("""
default_behavior: deny
permissions: invalid
""")
	
	with pytest.raises(ValidationError) as exec_info:
		load_policy(file)

	assert "permissions" in str(exec_info.value)



