from enum import Enum
from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel
from src.models import Action, Dispensation
from src.audit import AuditLogger
import asyncio

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



class ObligationManager:

	def __init__(self, poll_interval_seconds: int = 5, audit_logger: Optional[AuditLogger] = None):
		self._obligations: dict[str, ObligationRecord] = {}
		self._poll_interval = poll_interval_seconds
		self._poll_task: Optional[asyncio.Task] = None
		self.audit_logger = audit_logger

	
	def register(
		self,
		obligation_id: str,
		permission_id: str,
		subject: str,
		obliged_action: str,
		deadline_minutes: int,
		fulfillment_constraint: dict = None
	):
		"""
		Called by PolicyEngine when permission with provisions fires.
		"""

		now = datetime.now(timezone.utc)
		record= ObligationRecord(
			id=f"{obligation_id}_{now.isoformat()}_{subject}",
			obligation_id=obligation_id,
			permission_id=permission_id,
			subject=subject,
			obliged_action=obliged_action,
			deadline= now + timedelta(minutes=deadline_minutes),
			fulfillment_constraint= fulfillment_constraint or {}
		)

		self._obligations[record.id] = record

		if self.audit_logger:
			self.audit_logger.log_obligation(record, "CREATED")

		return record
	

	def check_fulfillment(self, action: Action) -> Optional[ObligationRecord]:
		"""
		Called by middleware when any action occurs.
		if this action matches a PENDING obligation's obliged_action,
		mark it FULFILLED and return the record. 
		"""

		for record in self._obligations.values():
			if record.status != "PENDING":
				continue

			if action.action_type == record.obliged_action:
				if action.subject == record.subject:
					record.status = ObligationStatus.FULFILLED
					record.fulfilled_at = datetime.now(timezone.utc)

					if self.audit_logger:
						self.audit_logger.log_obligation(record, "FULFILLED", action)
					return record
				

		return None
	

	def _check_deadlines(self):
		"""
		Synchronous check called by polling loop.
		"""

		now = datetime.now(timezone.utc)

		for record in self._obligations.values():
			if record.status == ObligationStatus.PENDING and now > record.deadline:
				record.status = ObligationStatus.VIOLATED
				record.violated_at = now

				if self.audit_logger:
					self.audit_logger.log_obligation(record, "VIOLATED")


	async def start_polling(self):
		"""
		Background task, start calling at system startup
		"""

		while True:
			self._check_deadlines()
			await asyncio.sleep(self._poll_interval)


	def start(self):
		"""
		Fire and forget the polling loop
		"""

		self._poll_task = asyncio.create_task(self.start_polling())


	def stop(self):
		"""
		Stop background task
		"""

		if self._poll_task:
			self._poll_task.cancel()

	def get_obligations(self, status: Optional[ObligationStatus] = None) -> list[ObligationRecord]:
		"""
		Get obligations based on status
		"""

		records = list(self._obligations.values())

		if status: 
			records = [r for r in records if r.status == status]

		return records
	


	def check_dispensation(self, action: Action, dispensations: list[Dispensation]) -> Optional[ObligationRecord]:
		"""
		Check if any dispensation rule matches the current context.
		if so it waives the named obligation
		"""

		for disp in dispensations:
			if self._constraint_match(action.context, disp.constraint):
				for record in self._obligations.values():
					if (record.status == ObligationStatus.PENDING and record.obligation_id == disp.waives):
						record.status = ObligationStatus.WAIVED
						record.waived_at = datetime.now(timezone.utc)
						record.waived_by = disp.id

						if self.audit_logger:
							self.audit_logger.log_obligation(record, "WAIVED")
						
						return record
					
		return None

	


	def _constraint_match(self, context: dict, constraint: dict) -> bool:

		for key, expected in constraint.items():
			if key not in context or context[key] != expected:
				return False
		return True