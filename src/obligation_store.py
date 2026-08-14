import json
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker
from src.models import ObligationRecord, ObligationStatus
from src.db import Base, Session, init_db


class ObligationEntry(Base):
	__tablename__ = "obligations"

	id = Column(String, primary_key=True)
	obligation_id = Column(String, nullable=False)
	permission_id = Column(String, nullable=False, default="unknown")
	subject = Column(String, nullable=False)
	obliged_action = Column(String, nullable=False)
	deadline = Column(DateTime, nullable=False)
	status = Column(String, nullable=False)
	fulfilled_at = Column(DateTime)
	violated_at = Column(DateTime)
	waived_at = Column(DateTime)
	waived_by = Column(String)
	fulfillment_constraint = Column(String, nullable=False, default="{}")


class ObligationStore:

	def __init__(self, db_path: str = None):
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
		return self._session_local()

	def _to_entry(self, record: ObligationRecord) -> ObligationEntry:
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
		with self._session() as session:
			entries = session.query(ObligationEntry).all()
			return [self._from_entry(e) for e in entries]