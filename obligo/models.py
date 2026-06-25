from pydantic import BaseModel, ValidationError
from typing import Dict, Any, Literal
from pathlib import Path
import yaml

class Action(BaseModel):
	subject: str
	action_type: str
	resource: str
	context: Dict[str, Any]


class Permission(BaseModel):
	id: str
	action: str
	constraint: Dict[str, Any]
	provisions: list[str] = []


class Prohibition(BaseModel):
	id: str
	action: str
	constraint: Dict[str, Any]


class Obligation(BaseModel):
	id: str
	obliged_action: str
	deadline_minutes: int
	description: str


class Dispensation(BaseModel):
	id: str
	constraint: Dict[str, Any]
	waives: str


class RulePriority(BaseModel):
	id: str
	greater: str
	lesser: str


class PolicySet(BaseModel):
	permissions: list[Permission] = []
	prohibitions: list[Prohibition] = []
	obligations: list[Obligation] = []
	dispensations: list[Dispensation] = []
	rule_priorities: list[RulePriority] = []
	default_behavior: Literal["explicit_permit_implicit_prohibit", "explicit_permit_explicit_prohibit"]



def load_policy(path: str | Path) -> PolicySet:

	with open(path, "r", encoding="utf-8") as f:
		data = yaml.safe_load(f)

		if data is None:
			raise ValueError("YAML file is empty")
		
		return PolicySet.model_validate(data)
