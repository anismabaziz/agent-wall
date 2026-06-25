from typing import Optional
from obligo.models import RulePriority



class ConflictResolver:

	def __init__(self, rule_priorities: list[RulePriority]):
		
		# lookup map for fast access
		self._priority_map = {
			(rp.greater, rp.lesser): rp for rp in rule_priorities
		}

	def resolve(self, permission_ids: list[str], prohibition_ids: list[str]) -> Optional[tuple[str, str]]:


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

