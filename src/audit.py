from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base, Session
from src.models import Action, ObligationRecord, Verdict


class AuditEntry(Base):
	"""
	Represents a single row in the audit log: everything that was requested,
	decided, and any obligation lifecycle event that accompanied it.
"""
	__tablename__ = "audit_log"

	id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
	timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

	# what happened
	action_subject: Mapped[str]
	action_type: Mapped[str]
	action_resource: Mapped[Optional[str]]

	# the decision
	verdict: Mapped[str]
	explanation: Mapped[str]
	matched_rule_ids: Mapped[Optional[str]]

	# obligation lifecycle events
	obligation_id: Mapped[Optional[str]]
	obligation_status_change: Mapped[Optional[str]]

	# policy version
	policy_file: Mapped[str]


class AuditLogger:

	"""
	Persists decision and obligation events to the SQLite audit store and
	offers a queryable view over them.
"""

	def __init__(self, policy_file: str = "unknown"):
		"""
		Create a logger bound to a specific policy file, so every entry it
		writes records which policy version produced the decision.
"""
		self.policy_file = policy_file


	def log_decision(
			self, 
			action: Action, 
			verdict: Verdict, 
			matched_rule_ids: Optional[list[str]] = None,
			obligation_change: Optional[tuple[str, str]] = None # (obl_id, status)
			):
		"""
		Record an authorization decision (and any resulting obligation status
		change) as a new row in the audit log, returning its id.
"""
		with Session() as session:
			entry = AuditEntry(
				action_subject=action.subject,
				action_type=action.action_type,
				action_resource=action.resource,
				verdict=verdict.decision,
				explanation=verdict.explanation,
				matched_rule_ids=",".join(matched_rule_ids or []),
				policy_file=self.policy_file,
				obligation_id=obligation_change[0] if obligation_change else None,
				obligation_status_change=obligation_change[1] if obligation_change else None
			)
			
			session.add(entry)
			session.commit()

			return entry.id
		

	def log_obligation(self, obligation_record: ObligationRecord, event: str, action: Optional[Action] = None):

		"""
		Append an obligation lifecycle event (e.g. registered, fulfilled,
		violated) to the audit log, associating it with the record and the
		action that triggered it when available.
"""
		with Session() as session:
			entry = AuditEntry(
				action_subject=action.subject if action else obligation_record.subject,
				action_type=action.action_type if action else f"obligation: {obligation_record.obligation_id}",
				action_resource=action.resource if action else "",
				verdict=f"OBLIGATION_{event}",
				explanation=f"Obligation {obligation_record.id} {event.lower()}",
				obligation_id=obligation_record.id,
				obligation_status_change=event,
				policy_file=self.policy_file
			)

			session.add(entry)
			session.commit()

		

	def query(self, limit: int = 100, offset: int = 0):

		"""
		Fetch audit entries ordered newest-first, as a list of plain dicts,
		supporting pagination via limit and offset.
"""
		with Session() as session:

			entries = session.query(AuditEntry)\
				.order_by(AuditEntry.timestamp.desc())\
				.limit(limit)\
				.offset(offset)\
				.all()
			

			return [
				{
					"id": e.id,
					"timestamp": e.timestamp.isoformat(),
					"action": f"{e.action_subject} {e.action_type} {e.action_resource}",
					"verdict": e.verdict,
					"explanation": e.explanation,
					"matched_rules": e.matched_rule_ids,
					"obligation_change": f"{e.obligation_id}: {e.obligation_status_change}" if e.obligation_id else None
				}
				for e in entries
			]

