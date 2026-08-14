from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import yaml
from pydantic import BaseModel


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
	# Fallback decision when nothing matches in explicit_permit_explicit_prohibit mode.
	default_decision: Literal["DENY", "PERMIT", "PROHIBIT"] = "DENY"



class Verdict(BaseModel):
	decision: Literal["PERMIT", "PROHIBIT", "DEFAULT_DENY"]
	explanation: str
	obligations: list[str] = []
	permission_ids: list[str] = []



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
	path = Path(path)

	if not path.is_absolute():
		# resolve relative to the repo root so callers work from any CWD
		path = Path(__file__).resolve().parent.parent / path

	with open(path, "r", encoding="utf-8") as f:
		data = yaml.safe_load(f)

		if data is None:
			raise ValueError("YAML file is empty")
		
		return PolicySet.model_validate(data)
