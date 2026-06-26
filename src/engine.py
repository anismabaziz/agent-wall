from pydantic import BaseModel
from typing import Literal
from src.models import PolicySet, Action, Permission, Prohibition
from src.conflict import ConflictResolver

class Verdict(BaseModel):
	decision: Literal["PERMIT", "PROHIBIT", "DEFAULT_DENY"]
	explanation: str
	obligations: list[str] = []



class PolicyEngine:

	def __init__(self, policy_set: PolicySet):
		self.policy_set = policy_set
		self.conflict_resolver = ConflictResolver(policy_set.rule_priorities)

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
		try:
			return self._evaluate(action)
		except Exception as e:
			return Verdict(
				decision="DEFAULT_DENY",
				explanation=f"Policy engine internal error ({type(e).__name__}): {e}",
				obligations=[]
			)


	def _evaluate(self, action: Action) -> Verdict:
		
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


		def _obligations_from(perms: list[Permission]) -> list[str]:
			result = []
			seen = set()

			for perm in perms:
				for obl_id in perm.provisions or []:
					if obl_id not in seen:
						seen.add(obl_id)
						result.append(obl_id)
			
			return result



		if has_perms and not has_prohs:
			return Verdict(
				decision="PERMIT",
				explanation= "Permitted by rules: " + ", ".join(p.id for p in matched_permissions),
				obligations=_obligations_from(matched_permissions)
			)
		
		if has_prohs and not has_perms:
			return Verdict(
				decision="PROHIBIT",
				explanation="Prohibited by rules: " + ", ".join(p.id for p in matched_prohibitions),
				obligations=[]
			)
		

		if has_perms and has_prohs:

			resolution = self.conflict_resolver.resolve(
				[p.id for p in matched_permissions],
				[p.id for p in matched_prohibitions]
			)

			if resolution:
				winning_id, priority_id = resolution

				if winning_id in [p.id for p in matched_permissions]:

					winning_perm = next(p for p in matched_permissions if p.id == winning_id)

					return Verdict(
						decision="PERMIT",
						explanation=f"Resolved by RulePriority {priority_id}: {winning_id} outranks conflicting prohibition(s)",
						obligations=_obligations_from([winning_perm])
					)
				else:
					return Verdict(
						decision="PROHIBIT",
						explanation=f"Resolved by RulePriority {priority_id}: {winning_id} outranks conflicting permission(s)",
						obligations=[]
					)
			
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



