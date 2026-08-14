from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Integer
from src.models import Action, Verdict, ObligationRecord
from src.db import Base, Session

class AuditEntry(Base):
	__tablename__ = "audit_log"

	id = Column(Integer, primary_key=True, autoincrement=True)
	timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

	# what happened
	action_subject = Column(String, nullable=False)
	action_type = Column(String, nullable=False)
	action_resource = Column(String)

	# the decision
	verdict = Column(String, nullable=False)
	explanation = Column(String, nullable=False)
	matched_rule_ids = Column(String)

	# obligation lifecycle events
	obligation_id = Column(String)
	obligation_status_change = Column(String)

	# policy version
	policy_file = Column(String, nullable=False)


class AuditLogger:

	def __init__(self, policy_file: str = "unknown"):
		self.policy_file = policy_file


	def log_decision(
			self, 
			action: Action, 
			verdict: Verdict, 
			matched_rule_ids: list[str] = None,
			obligation_change: tuple[str, str] = None # (obl_id, status)
			):
		
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
		

	def log_obligation(self, obligation_record: ObligationRecord, event: str, action: Action = None):

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

