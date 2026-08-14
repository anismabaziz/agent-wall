import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Configurable DB path. Override with the AGENT_WALL_AUDIT_DB env var;
# otherwise default to <repo root>/agent_wall_audit.db regardless of CWD.
_db_path = os.environ.get("AGENT_WALL_AUDIT_DB", "agent_wall_audit.db")

if not os.path.isabs(_db_path):
	_db_path = str(Path(__file__).resolve().parent.parent / _db_path)

engine = create_engine(f"sqlite:///{_db_path}", echo=False)


class Base(DeclarativeBase):
	"""
	Declarative base shared by all ORM models so their tables can be created
	together against the single configured engine.
"""


Session = sessionmaker(bind=engine)


def resolve_db_path() -> str:
	"""
	Resolve the absolute path of the SQLite audit database, honouring the
	AGENT_WALL_AUDIT_DB override and defaulting to the repo root.
"""
	path = os.environ.get("AGENT_WALL_AUDIT_DB", "agent_wall_audit.db")
	if not os.path.isabs(path):
		path = str(Path(__file__).resolve().parent.parent / path)
	return path


def init_db() -> None:
	"""
	Create tables for all registered models, importing them first so they
	are declared on the shared Base.
"""
	from src import audit, obligation_store  # noqa: F401  (register tables on Base)
	Base.metadata.create_all(engine)
	_migrate()


def _migrate() -> None:
	"""
	Additively migrate existing databases. create_all() will not add columns to
	tables that already exist, so apply lightweight ALTERs for newly-introduced
	columns here to keep older DB files (and dev instances) working.
"""
	cols = {c["name"] for c in inspect(engine).get_columns("audit_log")} if inspect(engine).has_table("audit_log") else set()
	if cols and "policy_version" not in cols:
		with engine.begin() as conn:
			conn.execute(text("ALTER TABLE audit_log ADD COLUMN policy_version VARCHAR"))