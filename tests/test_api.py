import os
import tempfile

# Must point the app at an isolated DB before importing src.api,
# since db.engine is created at import time from this env var.
_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["AGENT_WALL_AUDIT_DB"] = _db_path

from fastapi.testclient import TestClient

import src.api as api
from src.models import ObligationStatus
from src.obligation_store import ObligationStore
from src.obligations import ObligationManager
from src.audit import AuditLogger


def _annotation_func():
	pass


def _fresh_manager() -> ObligationManager:
	"""Install a fresh manager backed by an isolated temp store into API globals."""
	import uuid
	path = os.path.join(tempfile.gettempdir(), f"aw_api_{uuid.uuid4().hex}.db")
	store = ObligationStore(path)
	manager = ObligationManager(poll_interval_seconds=10, audit_logger=None, store=store)
	api.obligation_manager = manager
	return manager


def _register(manager: ObligationManager, subject: str, obligation_id: str,
			  permission_id: str, constraint: dict) -> None:
	manager.register(
		obligation_id=obligation_id,
		permission_id=permission_id,
		subject=subject,
		obliged_action="file_ctr",
		deadline_minutes=60,
		fulfillment_constraint=constraint,
	)


def test_obligations_response_includes_permission_id_and_constraint():
	manager = _fresh_manager()
	client = TestClient(api.app)
	_register(manager, "alice", "Ob_FileCTR", "Perm_FileCTR", {"report_to": "compliance"})

	records = client.get("/obligations").json()
	assert len(records) == 1

	record = records[0]
	assert record["permission_id"] == "Perm_FileCTR"
	assert record["fulfillment_constraint"] == {"report_to": "compliance"}
	assert record["obligation_id"] == "Ob_FileCTR"
	assert record["subject"] == "alice"


def test_obligations_pagination_limit_and_offset():
	manager = _fresh_manager()
	client = TestClient(api.app)
	for i in range(5):
		_register(manager, f"user_{i}", f"Ob_{i}", f"Perm_{i}", {})

	page = client.get("/obligations", params={"limit": 2, "offset": 0}).json()
	assert len(page) == 2

	next_page = client.get("/obligations", params={"limit": 2, "offset": 2}).json()
	ids_page = {r["subject"] for r in page}
	ids_next = {r["subject"] for r in next_page}
	assert ids_page.isdisjoint(ids_next)

	all_records = client.get("/obligations", params={"limit": 100}).json()
	assert len(all_records) == 5


def test_obligations_loads_persisted_records():
	manager = _fresh_manager()
	client = TestClient(api.app)
	_register(manager, "carol", "Ob_Persist", "Perm_Persist", {"proof": True})

	# Reload from the persisted store, simulating a process restart.
	manager._obligations.clear()
	manager.load()

	records = client.get("/obligations").json()
	assert len(records) == 1
	assert records[0]["permission_id"] == "Perm_Persist"
	assert records[0]["fulfillment_constraint"] == {"proof": True}


def test_obligations_status_filter_still_works():
	manager = _fresh_manager()
	client = TestClient(api.app)
	_register(manager, "dave", "Ob_A", "Perm_A", {})

	record = next(iter(manager._obligations.values()))
	record.status = ObligationStatus.VIOLATED

	resp = client.get("/obligations", params={"status": "PENDING"}).json()
	assert resp == []

	resp = client.get("/obligations", params={"status": "VIOLATED"}).json()
	assert len(resp) == 1
	assert resp[0]["status"] == "VIOLATED"