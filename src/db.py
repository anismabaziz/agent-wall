import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Configurable DB path. Override with the AGENT_WALL_AUDIT_DB env var;
# otherwise default to <repo root>/agent_wall_audit.db regardless of CWD.
_db_path = os.environ.get("AGENT_WALL_AUDIT_DB", "agent_wall_audit.db")

if not os.path.isabs(_db_path):
	_db_path = str(Path(__file__).resolve().parent.parent / _db_path)

engine = create_engine(f"sqlite:///{_db_path}", echo=False)
Base = declarative_base()
Session = sessionmaker(bind=engine)


def resolve_db_path() -> str:
	path = os.environ.get("AGENT_WALL_AUDIT_DB", "agent_wall_audit.db")
	if not os.path.isabs(path):
		path = str(Path(__file__).resolve().parent.parent / path)
	return path


def init_db() -> None:
	"""Create tables for all registered models, importing them first."""
	from src import audit, obligation_store  # noqa: F401  (register tables on Base)
	Base.metadata.create_all(engine)