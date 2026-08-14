import asyncio
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.audit import AuditLogger
from src.models import Action, Dispensation, ObligationRecord, ObligationStatus


class ObligationManager:

	def __init__(self, poll_interval_seconds: int = 5, audit_logger: Optional[AuditLogger] = None, store=None):
		self._obligations: dict[str, ObligationRecord] = {}
		self._poll_interval = poll_interval_seconds
		self._poll_task: Optional[asyncio.Task] = None
		self.audit_logger = audit_logger
		self.store = store
		self._lock = threading.RLock()


	def load(self) -> None:
		"""
		Load persisted obligations from the store into memory (e.g. on startup).
		Only obligations that are still open (PENDING/WAIVED/FULFILLED) are kept;
		VIOLATED records are kept too so history is available in memory.
		"""
		if not self.store:
			return

		with self._lock:
			for record in self.store.load_all():
				self._obligations[record.id] = record


	def register(
		self,
		obligation_id: str,
		permission_id: str,
		subject: str,
		obliged_action: str,
		deadline_minutes: int,
		fulfillment_constraint: Optional[dict] = None
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

		with self._lock:
			self._obligations[record.id] = record

		if self.store:
			self.store.save(record)

		if self.audit_logger:
			self.audit_logger.log_obligation(record, "CREATED")

		return record
	

	def check_fulfillment(self, action: Action) -> Optional[ObligationRecord]:
		"""
		Called by middleware when any action occurs.
		if this action matches a PENDING obligation's obliged_action,
		mark it FULFILLED and return the record. 
		"""

		with self._lock:
			for record in self._obligations.values():
				if record.status != "PENDING":
					continue

				if action.action_type == record.obliged_action:
					if action.subject == record.subject:
						# the fulfilling action must satisfy the obligation's constraints
						if not self._constraint_match(action.context, record.fulfillment_constraint):
							continue

						record.status = ObligationStatus.FULFILLED
						record.fulfilled_at = datetime.now(timezone.utc)

						if self.store:
							self.store.save(record)

						if self.audit_logger:
							self.audit_logger.log_obligation(record, "FULFILLED", action)
						return record
				

		return None
	

	def _check_deadlines(self):
		"""
		Synchronous check called by polling loop.
		"""

		now = datetime.now(timezone.utc)

		with self._lock:
			for record in self._obligations.values():
				if record.status == ObligationStatus.PENDING and now > record.deadline:
					record.status = ObligationStatus.VIOLATED
					record.violated_at = now

					if self.store:
						self.store.save(record)

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

		with self._lock:
			for disp in dispensations:
				if self._constraint_match(action.context, disp.constraint):
					for record in self._obligations.values():
						if (record.status == ObligationStatus.PENDING and record.obligation_id == disp.waives):
							record.status = ObligationStatus.WAIVED
							record.waived_at = datetime.now(timezone.utc)
							record.waived_by = disp.id

							if self.store:
								self.store.save(record)

							if self.audit_logger:
								self.audit_logger.log_obligation(record, "WAIVED")
							
							return record
						
		return None


	def enforce(self, action: Action, dispensations: Optional[list[Dispensation]] = None,
				check_deadline: bool = True) -> dict:
		"""
		Apply the deterministic event ordering: dispensation -> fulfillment -> deadline.

		When multiple events arrive together the outcome is guaranteed and
		documented, so consumers never depend on registration quirks:

		  1. dispensation: matching PENDING obligations are waived first
		  2. fulfillment:  a PENDING obligation matching this action is fulfilled
		  3. deadline:      remaining PENDING obligations past their deadline become
		                     VIOLATED

		Wrapping the sequence in a single lock makes the order atomic with
		respect to concurrent events.

		Returns:
			A dict with outcome summaries:
			  {"dispensation": list[ObligationRecord], "fulfilled": ObligationRecord|None}"
		"""
		outcomes: dict[str, Any] = {"dispensation": [], "fulfilled": None}

		with self._lock:
			for disp in (dispensations or []):
				waived = self.check_dispensation(action, [disp])
				if waived is not None:
					outcomes["dispensation"].append(waived)

			outcomes["fulfilled"] = self.check_fulfillment(action)

			if check_deadline:
				self._check_deadlines()

		return outcomes

	


	def _constraint_match(self, context: dict, constraint: dict) -> bool:

		for key, expected in constraint.items():
			if key not in context or context[key] != expected:
				return False
		return True