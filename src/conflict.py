from typing import Optional

from src.models import RulePriority


class ConflictResolver:

	"""
	Resolves conflicts between permissions and prohibitions using the
	configured RulePriority map, returning the winning rule and the priority
	that decided it (or None when no explicit priority applies).
"""

	def __init__(self, rule_priorities: list[RulePriority]):
		"""
		Build a lookup map from (greater, lesser) rule id pairs so resolution
		can be answered in O(1) per pair.
"""

		# lookup map for fast access
		self._priority_map = {
			(rp.greater, rp.lesser): rp for rp in rule_priorities
		}

	def resolve(self, permission_ids: list[str], prohibition_ids: list[str]) -> Optional[tuple[str, str]]:
		"""
		Determine whether any permission outranks a prohibition (or vice
		versa). Returns (winning_rule_id, priority_id) or None if no priority
		relationship resolves the conflict.
"""

		# check if there is a permission that outranks a prohibition
		for perm_id in permission_ids:
			for proh_id in prohibition_ids:
				if (perm_id, proh_id) in self._priority_map:
					rp = self._priority_map[(perm_id, proh_id)]
					return (perm_id, rp.id)

		# check if there is a prohibition that outranks a permission
		for perm_id in permission_ids:
			for proh_id in prohibition_ids:
				if (proh_id, perm_id) in self._priority_map:
					rp = self._priority_map[(proh_id, perm_id)]
					return (proh_id, rp.id)

		return None

