from typing import Optional
from src.models import PolicySet, Action, Permission, Prohibition, Verdict
from src.conflict import ConflictResolver
from src.audit import AuditLogger


class PolicyEngine:

	def __init__(self, policy_set: PolicySet, audit_logger: Optional[AuditLogger] = None):
		self.policy_set = policy_set
		self.conflict_resolver = ConflictResolver(policy_set.rule_priorities)
		self.audit_logger = audit_logger

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

			verdict = Verdict(
				decision="DEFAULT_DENY",
				explanation=f"Policy engine internal error ({type(e).__name__}): {e}",
				obligations=[]
			)

			if self.audit_logger:
				self.audit_logger.log_decision(
					action=action,
					verdict=verdict
				)

			return verdict


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
		

		def _log(verdict: Verdict, matched_rules: list = None):
			if self.audit_logger:
				self.audit_logger.log_decision(
					action=action,
					verdict=verdict,
					matched_rule_ids=[r.id for r in matched_rules] or []
				)

			return verdict




		# only permissions match => PERMIT
		if has_perms and not has_prohs:
			verdict = Verdict(
				decision="PERMIT",
				explanation= "Permitted by rules: " + ", ".join(p.id for p in matched_permissions),
				obligations=_obligations_from(matched_permissions),
				permission_ids=[p.id for p in matched_permissions]
			)
			return _log(verdict, matched_permissions)
		
		# only prohibitions match => PROHIBIT
		if has_prohs and not has_perms:
			verdict = Verdict(
				decision="PROHIBIT",
				explanation="Prohibited by rules: " + ", ".join(p.id for p in matched_prohibitions),
				obligations=[]
			)
			return _log(verdict, matched_prohibitions)
		

		# both match => conflict resolution part
		if has_perms and has_prohs:
			resolution = self.conflict_resolver.resolve(
				[p.id for p in matched_permissions],
				[p.id for p in matched_prohibitions]
			)

			if resolution:
				winning_id, priority_id = resolution

				if winning_id in [p.id for p in matched_permissions]:

					winning_perm = next(p for p in matched_permissions if p.id == winning_id)
					verdict = Verdict(
						decision="PERMIT",
						explanation=f"Resolved by RulePriority {priority_id}: {winning_id} outranks conflicting prohibition(s)",
						obligations=_obligations_from([winning_perm]),
						permission_ids=[winning_id]
					)
					return _log(verdict, matched_permissions + matched_prohibitions)
				
				else:

					verdict = Verdict(
						decision="PROHIBIT",
						explanation=f"Resolved by RulePriority {priority_id}: {winning_id} outranks conflicting permission(s)",
						obligations=[]
					)
					return _log(verdict, matched_permissions + matched_prohibitions)
			

			# unresolved conflict
			verdict = Verdict(
				decision="DEFAULT_DENY",
				explanation=f"Unresolved conflict: permissions [{", ".join(p.id for p in matched_permissions)}] vs prohibitions [{", ".join(p.id for p in matched_prohibitions)}]",
				obligations=[]
			)
			return _log(verdict, matched_permissions + matched_prohibitions)


		# nothing matches => honor default_behavior
		if self.policy_set.default_behavior == "explicit_permit_implicit_prohibit":
			decision, reason = "DEFAULT_DENY", "No matching permission rules found"
		else:
			match self.policy_set.default_decision:
				case "PERMIT":
					decision, reason = "PERMIT", "No explicit rule; default permits"
				case "PROHIBIT":
					decision, reason = "PROHIBIT", "No explicit rule; default prohibits"
				case _:
					decision, reason = "DEFAULT_DENY", "No matching rule; default deny"

		verdict = Verdict(
			decision=decision,
			explanation=reason,
			obligations=[]
		)
		return _log(verdict, matched_permissions + matched_prohibitions)


	def register_obligations(self, obligation_manager, verdict: Verdict, subject: str) -> list:
		"""
		Central registration of obligations produced by a verdict.

		Looks up each obligation template from the policy set and registers a
		runtime record via the obligation manager, attributing it to the permission
		that provisions it (falling back to "unknown").
		"""
		if verdict.decision != "PERMIT" or not verdict.obligations:
			return []

		provision_owner: dict[str, str] = {}
		for permission in self.policy_set.permissions:
			for obl in permission.provisions or []:
				provision_owner.setdefault(obl, permission.id)

		records = []
		for obl_id in verdict.obligations:
			obligation = next((o for o in self.policy_set.obligations if o.id == obl_id), None)
			if obligation is None:
				continue

			records.append(
				obligation_manager.register(
					obligation_id=obl_id,
					permission_id=provision_owner.get(obl_id, "unknown"),
					subject=subject,
					obliged_action=obligation.obliged_action,
					deadline_minutes=obligation.deadline_minutes,
				)
			)

		return records



