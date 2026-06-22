from pydantic import BaseModel
from typing import Literal
from obligo.models import PolicySet, Action, Permission, Prohibition

class Verdict(BaseModel):
	decision: Literal["PERMIT", "PROHIBIT", "DEFAULT_DENY"]
	explanation: str
	obligations: list[str] = []



class PolicyEngine:

	def __init__(self, policy_set: PolicySet):
		self.policy_set = policy_set

	def _matches(self, action: Action, rule: Permission | Prohibition) -> bool:

		if rule.action != action.action_type:
			return False
		
		for key, expected_value in rule.constraint.items():
			if key not in action.context:
				return False
			
			if action.context[key] != expected_value:
				return False
			
		return True
	

	def evaluate(self, action: Action) -> Verdict:
		
		matched_permissions = []
		matched_prohibitions = []

		for permission in self.policy_set.permissions:
			if self._matches(action, permission):
				matched_permissions.append(permission)

		for prohibition in self.policy_set.prohibitions:
			if self._matches(action, prohibition):
				matched_prohibitions.append(prohibition)


		has_perms = bool(matched_permissions)
		has_prohs = bool(matched_prohibitions)


		if has_perms and not has_prohs:
			return Verdict(
				decision="PERMIT",
				explanation= "Permitted by rules: " + ", ".join(p.id for p in matched_permissions),
				obligations=[]
			)
		
		if has_prohs and not has_perms:
			return Verdict(
				decision="PROHIBIT",
				explanation="Prohibited by rules: " + ", ".join(p.id for p in matched_prohibitions),
				obligations=[]
			)
		

		if has_perms and has_prohs:
			return Verdict(
				decision="DEFAULT_DENY",
				explanation=f"Unresolved conflict: permissions [{", ".join(p.id for p in matched_permissions)}] vs prohibitions [{", ".join(p.id for p in matched_prohibitions)}]",
				obligations=[]
			)


		return Verdict(
			decision="DEFAULT_DENY",
			explanation="No matching permission rules found",
			obligations=[]
		)



