from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import yaml
from pydantic import BaseModel


class Action(BaseModel):
	"""
	Describes a single access-control request that the policy engine
	evaluates against the configured rules.
"""
	subject: str
	action_type: str
	resource: str
	context: Dict[str, Any]


class Permission(BaseModel):
	"""
	Represents a rule that grants a subject the right to perform an action
	on a resource, subject to any declared constraints.
"""
	id: str
	action: str
	constraint: Dict[str, Any]
	provisions: list[str] = []


class Prohibition(BaseModel):
	"""
	Represents a rule that denies a subject the right to perform an action
	on a resource, subject to any declared constraints.
"""
	id: str
	action: str
	constraint: Dict[str, Any]


class Obligation(BaseModel):
	"""
	Models a must-do action that must be fulfilled within a deadline once a
	permission is granted.
"""
	id: str
	obliged_action: str
	deadline_minutes: int
	description: str


class Dispensation(BaseModel):
	"""
	Represents a waiver that exempts a subject from a specific obligation.
"""
	id: str
	constraint: Dict[str, Any]
	waives: str


class RulePriority(BaseModel):
	"""
	Declares an ordering where one rule outranks another when both match a
	request, resolving conflicts between permissions and prohibitions.
"""
	id: str
	greater: str
	lesser: str


class OntologyClass(BaseModel):
	"""
	Declares a single class in the lightweight type ontology (a small DAG).
	Each class lists its parent classes via `subClassOf` so a rule expressed
	over a class automatically covers its subclasses.
"""
	id: str
	subClassOf: list[str] = []


class PolicySet(BaseModel):
	"""
	The top-level container of all policy rules, listing every permission,
	prohibition, obligation, dispensation, and rule priority plus the
	behaviour to apply when no explicit rule matches.
"""
	permissions: list[Permission] = []
	prohibitions: list[Prohibition] = []
	obligations: list[Obligation] = []
	dispensations: list[Dispensation] = []
	rule_priorities: list[RulePriority] = []
	# Lightweight type ontology used by the `matches_type` constraint.
	ontology: list[OntologyClass] = []
	# Named trusted issuers whose credentials are honoured by `credential`.
	credential_authorities: list[str] = []
	default_behavior: Literal["explicit_permit_implicit_prohibit", "explicit_permit_explicit_prohibit"]
	# Fallback decision when nothing matches in explicit_permit_explicit_prohibit mode.
	default_decision: Literal["DENY", "PERMIT", "PROHIBIT"] = "DENY"



class Verdict(BaseModel):
	"""
	Encapsulates the outcome of evaluating an action, including the final
	decision, a human-readable explanation, and any resulting obligations.
"""
	decision: Literal["PERMIT", "PROHIBIT", "DEFAULT_DENY"]
	explanation: str
	obligations: list[str] = []
	permission_ids: list[str] = []



class ObligationStatus(str, Enum):
	"""
	Enumerates the lifecycle states a runtime obligation record can be in.
"""
	PENDING = "PENDING"
	FULFILLED = "FULFILLED"
	VIOLATED = "VIOLATED"
	WAIVED = "WAIVED"

class ObligationRecord(BaseModel):
	"""
	Stores the runtime, stateful record of a single obligation instance as
	it progresses toward fulfillment or violation.
"""
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
	"""
	Load a YAML policy file and validate it into a PolicySet, resolving a
	relative path against the repository root.
"""
	path = Path(path)

	if not path.is_absolute():
		# resolve relative to the repo root so callers work from any CWD
		path = Path(__file__).resolve().parent.parent / path

	with open(path, "r", encoding="utf-8") as f:
		data = yaml.safe_load(f)

		if data is None:
			raise ValueError("YAML file is empty")
		
		return PolicySet.model_validate(data)