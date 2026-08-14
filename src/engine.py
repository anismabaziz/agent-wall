from fnmatch import fnmatchcase
from typing import Literal, Optional

from src.audit import AuditLogger
from src.conflict import ConflictResolver
from src.models import Action, Permission, PolicySet, Prohibition, Verdict


def _to_number(value) -> Optional[float]:
	"""
	Best-effort numeric coercion for range operators. Returns None if not numeric.
"""
	if isinstance(value, bool):
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _wildcard_match(pattern: str, actual) -> bool:
	"""
	Match an actual value against a glob pattern, treating both as strings.
"""
	return fnmatchcase(str(actual), pattern)


def _contains(container, operand) -> bool:
	"""
	Check whether the container holds the operand, either as a single value
	or, when the operand is a list, as all of its items.
"""
	if isinstance(operand, list):
		return all(item in container for item in operand)
	return operand in container


def operator_match(actual, expected) -> bool:
	"""
	Evaluate a single constraint value `expected` against the action value `actual`.

	Supported forms (backward-compatible):
	  - plain scalar        -> equality (e.g. {"is_high_value": True})
	  - string with '*'     -> wildcard glob (e.g. "transaction://*")
	  - operator dict       -> {"gt": N} {"lt": N} {"gte": N} {"lte": N}
	                          {"neq": V} {"in": [...]} {"contains": [...]}
	                          {"wildcard": "..."}
"""
	if isinstance(expected, dict) and _is_operator_dict(expected):
		return _operator_dict_match(actual, expected)

	if isinstance(expected, str) and "*" in expected:
		return _wildcard_match(expected, actual)

	return actual == expected


def _is_operator_dict(value: dict) -> bool:
	"""
	Return True when the dict contains only recognised comparison operators.
"""
	operators = {"gt", "lt", "gte", "lte", "neq", "in", "contains", "wildcard"}
	return bool(value) and all(k in operators for k in value)


def _operator_dict_match(actual, expected: dict) -> bool:
	"""
	Evaluate every operator in a comparison-operator dict against the actual
	value, returning True only when all of them hold.
"""
	for op, operand in expected.items():
		if op in ("gt", "lt", "gte", "lte"):
			a = _to_number(actual)
			b = _to_number(operand)
			if a is None or b is None:
				return False
			ok = {
				"gt": a > b,
				"lt": a < b,
				"gte": a >= b,
				"lte": a <= b,
			}[op]
			if not ok:
				return False
		elif op == "neq":
			if actual == operand:
				return False
		elif op == "in":
			if actual not in operand:
				return False
		elif op == "contains":
			if not _contains(actual, operand):
				return False
		elif op == "wildcard":
			if not _wildcard_match(operand, actual):
				return False
	return True


class PolicyEngine:
	"""
	Core engine that evaluates an action against a policy set, applying
	conflict resolution and producing a verdict.

	Constraint handling includes the `matches_type` and `credential` forms so
	that decisions are determined by the machine, not the model: `matches_type`
	reasons over a type ontology and `credential` honours only verified,
	trusted-issuer passes.
"""

	def __init__(self, policy_set: PolicySet, audit_logger: Optional[AuditLogger] = None):
		"""
		Store the policy set, build a conflict resolver from its rule
		priorities, materialize the type ontology closure, and hold the
		optional audit logger.
"""
		self.policy_set = policy_set
		self.conflict_resolver = ConflictResolver(policy_set.rule_priorities)
		self.audit_logger = audit_logger
		self._class_closure = self._build_type_closure(policy_set.ontology)

	@staticmethod
	def _build_type_closure(ontology: list) -> dict[str, set]:
		"""
		Materialize, once at load time, the transitive subclass closure so a
		`matches_type` lookup over a parent class also covers every descendant.
"""
		if not ontology:
			return {}
		ancestors: dict[str, set] = {oc.id: set() for oc in ontology}
		changed = True
		while changed:
			changed = False
			for oc in ontology:
				for parent in oc.subClassOf:
					if parent not in ancestors:
						continue
					for a in ancestors[parent] | {parent}:
						if a not in ancestors[oc.id]:
							ancestors[oc.id].add(a)
							changed = True
		return {cls: ancestors[cls] | {cls} for cls in ancestors}

	def _matches(self, action: Action, rule: Permission | Prohibition) -> bool:
		"""
		Return True when the rule's action type and every constraint match the
		given action.
"""
		if rule.action != action.action_type:
			return False
		
		for key, expected in rule.constraint.items():
			if key == "matches_type":
				if not self._matches_type(action, expected):
					return False
				continue
			if key == "credential":
				if not self._matches_credential(action, expected):
					return False
				continue
			# subject/resource are always keyed; other keys must be present in context
			if key not in ("subject", "resource") and key not in action.context:
				return False
			actual = self._constraint_value(action, key)
			if not operator_match(actual, expected):
				return False
			
		return True

	def _matches_type(self, action: Action, class_name: str) -> bool:
		"""
		Return True when any of the action's staged resource types is a member
		of the class named by `class_name` (or one of its subclasses).
"""
		return self._constraint_type_match(action.context, class_name)

	def _matches_credential(self, action: Action, expected) -> bool:
		"""
		Return True only when the action presents a credential whose issuer is
		both in the policy's trusted authorities and, when the constraint names
		one, exactly matches it.
"""
		return self._constraint_credential_match(action.context, expected)

	def _constraint_type_match(self, context: dict, class_name: str) -> bool:
		"""
		Check the staged type list in a context dict against a class, following
		the subclass closure. A missing or empty type list never matches.
"""
		raw = context.get("_resource_types", [])
		types = raw if isinstance(raw, list) else [raw]
		for t in types:
			closure = self._class_closure.get(t, {t})
			if class_name in closure:
				return True
		return False

	def _constraint_credential_match(self, context: dict, expected) -> bool:
		"""
		Verify a staged credential issuer from a context dict against the policy's
		trusted authorities. No issuer, or an untrusted issuer, never matches.
"""
		issuer = context.get("_credential_issuer")
		if not issuer:
			return False
		if str(issuer) not in self.policy_set.credential_authorities:
			return False
		if expected is True:
			return True
		return str(issuer) == expected

	def constraint_match(self, context: dict, constraint: dict) -> bool:
		"""
		Match a bare context dict against a constraint dict (used by obligation
		dispensation and fulfillment checks so the same operators apply there).
"""
		for key, expected in constraint.items():
			if key == "matches_type":
				if not self._constraint_type_match(context, expected):
					return False
				continue
			if key == "credential":
				if not self._constraint_credential_match(context, expected):
					return False
				continue
			if key not in context:
				return False
			if not operator_match(context[key], expected):
				return False
		return True

	def _constraint_value(self, action: Action, key: str):
		"""
		Resolve a constraint key to an action value, honouring subject/resource scoping.
"""
		if key == "subject":
			return action.subject
		if key == "resource":
			return action.resource
		return action.context.get(key)
	

	def evaluate(self, action: Action) -> Verdict:
		"""
		Public entry point that evaluates the action and returns a verdict,
		converting any unexpected internal error into a default-deny verdict.
"""
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
		"""
		Match the action against all permissions and prohibitions, then apply
		conflict resolution or the default behaviour to produce a verdict.
"""
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
			"""
			Collect the IDs of the obligations derived from the matched permissions.
"""
			# central dedup of shared/provisioned obligations (issue #6)
			from src.derivations import derived_obligations
			return [o.id for o in derived_obligations(self.policy_set, [p.id for p in perms])]
		

		def _log(verdict: Verdict, matched_rules: Optional[list] = None):
			"""
			Audit the given verdict with the matched rules and return it.
"""
			if self.audit_logger:
				self.audit_logger.log_decision(
					action=action,
					verdict=verdict,
					matched_rule_ids=[r.id for r in (matched_rules or [])]
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
		decision: Literal["PERMIT", "PROHIBIT", "DEFAULT_DENY"]
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