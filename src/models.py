from pydantic import BaseModel
from typing import Dict, Any, Literal, Optional
from datetime import datetime
from pathlib import Path
from enum import Enum
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



class Verdict(BaseModel):
	decision: Literal["PERMIT", "PROHIBIT", "DEFAULT_DENY"]
	explanation: str
	obligations: list[str] = []



class ObligationStatus(str, Enum):
	PENDING = "PENDING"
	FULFILLED = "FULFILLED"
	VIOLATED = "VIOLATED"
	WAIVED = "WAIVED"

class ObligationRecord(BaseModel):
	id: str
	obligation_id: str
	permission_id: str
	subject: str
	obliged_action: str
	deadline: datetime
	status: ObligationStatus = ObligationStatus.PENDING
	fulfilled_at: Optional[datetime] = None
	violated_at: Optional[datetime] = None
	fulfillment_constraint: dict = {}
	waived_at: Optional[datetime] = None
	waived_by: Optional[str] = None


def load_policy(path: str | Path) -> PolicySet:

	with open(path, "r", encoding="utf-8") as f:
		data = yaml.safe_load(f)

		if data is None:
			raise ValueError("YAML file is empty")
		
		return PolicySet.model_validate(data)
