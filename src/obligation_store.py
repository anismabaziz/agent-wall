import json
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from src.db import Base, Session, init_db
from src.models import ObligationRecord, ObligationStatus


class ObligationEntry(Base):
	"""
	SQLAlchemy ORM model mapping an obligation to the "obligations" table.
"""

	__tablename__ = "obligations"

	id: Mapped[str] = mapped_column(primary_key=True)
	obligation_id: Mapped[str]
	permission_id: Mapped[str] = mapped_column(default="unknown")
	subject: Mapped[str]
	obliged_action: Mapped[str]
	deadline: Mapped[datetime]
	status: Mapped[str]
	fulfilled_at: Mapped[Optional[datetime]]
	violated_at: Mapped[Optional[datetime]]
	waived_at: Mapped[Optional[datetime]]
	waived_by: Mapped[Optional[str]]
	fulfillment_constraint: Mapped[str] = mapped_column(default="{}")


class ObligationStore:
	"""
	Persists and loads obligation records via SQLAlchemy, using either an
	isolated store for tests or the shared configured application database.
"""

	def __init__(self, db_path: Optional[str] = None):
		"""
		Set up the database session factory. When db_path is given, create an
		isolated SQLite engine bound to that path; otherwise reuse the shared
		configured session and initialize the database.
"""
		if db_path:
			# isolated store (used by tests against a temp DB)
			engine = create_engine(f"sqlite:///{db_path}", echo=False)
			Base.metadata.create_all(engine)
			self._session_local = sessionmaker(bind=engine)
		else:
			# shared application store using the configured DB
			self._session_local = Session
			init_db()

	def _session(self):
		"""
		Return a new session from the configured session factory.
"""
		return self._session_local()

	def _to_entry(self, record: ObligationRecord) -> ObligationEntry:
		"""
		Convert an ObligationRecord domain object into an ObligationEntry,
		serializing the fulfillment constraint to JSON for storage.
"""
		return ObligationEntry(
			id=record.id,
			obligation_id=record.obligation_id,
			permission_id=record.permission_id,
			subject=record.subject,
			obliged_action=record.obliged_action,
			deadline=record.deadline,
			status=record.status.value if hasattr(record.status, "value") else str(record.status),
			fulfilled_at=record.fulfilled_at,
			violated_at=record.violated_at,
			waived_at=record.waived_at,
			waived_by=record.waived_by,
			fulfillment_constraint=json.dumps(record.fulfillment_constraint or {}),
		)

	def _from_entry(self, entry: ObligationEntry) -> ObligationRecord:
		"""
		Convert an ObligationEntry into an ObligationRecord domain object,
		deserializing the fulfillment constraint from JSON.
"""
		return ObligationRecord(
			id=entry.id,
			obligation_id=entry.obligation_id,
			permission_id=entry.permission_id,
			subject=entry.subject,
			obliged_action=entry.obliged_action,
			deadline=entry.deadline,
			status=ObligationStatus(entry.status),
			fulfilled_at=entry.fulfilled_at,
			violated_at=entry.violated_at,
			waived_at=entry.waived_at,
			waived_by=entry.waived_by,
			fulfillment_constraint=json.loads(entry.fulfillment_constraint or "{}"),
		)

	def save(self, record: ObligationRecord) -> None:
		"""
		Upsert an obligation record into the database, inserting a new row when
		it does not exist or updating its mutable fields when it does.
"""
		entry = self._to_entry(record)
		with self._session() as session:
			existing = session.get(ObligationEntry, record.id)
			if existing is None:
				session.add(entry)
			else:
				for attr, value in {
					"status": entry.status,
					"fulfilled_at": entry.fulfilled_at,
					"violated_at": entry.violated_at,
					"waived_at": entry.waived_at,
					"waived_by": entry.waived_by,
					"fulfillment_constraint": entry.fulfillment_constraint,
				}.items():
					setattr(existing, attr, value)
			session.commit()

	def load_all(self) -> list[ObligationRecord]:
		"""
		Load and return every persisted obligation as an ObligationRecord.
"""
		with self._session() as session:
			entries = session.query(ObligationEntry).all()
			return [self._from_entry(e) for e in entries]