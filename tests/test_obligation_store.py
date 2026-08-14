import tempfile
import os
from pathlib import Path
from freezegun import freeze_time
from datetime import datetime, timedelta, timezone

from src.models import Action, ObligationStatus
from src.obligation_store import ObligationStore
from src.obligations import ObligationManager


def test_obligation_persists_across_restart(tmp_path):
	db_path = str(tmp_path / "obligations_test.db")

	# first "server": register a pending obligation, persisted to disk
	store1 = ObligationStore(db_path=db_path)
	manager1 = ObligationManager(store=store1)
	manager1.register(
		obligation_id="Ob_FileCTR",
		permission_id="Perm_ApprovedHighValue",
		subject="agent_1",
		obliged_action="file_ctr",
		deadline_minutes=60,
	)

	assert len(manager1.get_obligations(ObligationStatus.PENDING)) == 1
	del manager1, store1

	# second "server": new manager+store reads the obligation back from disk
	store2 = ObligationStore(db_path=db_path)
	manager2 = ObligationManager(store=store2)
	manager2.load()

	pending = manager2.get_obligations(ObligationStatus.PENDING)
	assert len(pending) == 1
	record = pending[0]
	assert record.obligation_id == "Ob_FileCTR"
	assert record.permission_id == "Perm_ApprovedHighValue"
	assert record.status == ObligationStatus.PENDING


def test_obligation_status_change_persists(tmp_path):
	db_path = str(tmp_path / "obligations_test2.db")

	store = ObligationStore(db_path=db_path)
	manager = ObligationManager(store=store)
	manager.register(
		obligation_id="Ob_NotifyCISO",
		permission_id="Perm_InstallSoftware",
		subject="agent_1",
		obliged_action="notify_ciso",
		deadline_minutes=60,
	)

	# fulfill it -> state change must be persisted
	manager.check_fulfillment(
		Action(subject="agent_1", action_type="notify_ciso", resource="c@x.com", context={})
	)
	assert manager.get_obligations(ObligationStatus.FULFILLED)

	# reload from disk: should be FULFILLED, not PENDING
	store2 = ObligationStore(db_path=db_path)
	manager2 = ObligationManager(store=store2)
	manager2.load()

	fulfilled = manager2.get_obligations(ObligationStatus.FULFILLED)
	assert len(fulfilled) == 1
	assert fulfilled[0].status == ObligationStatus.FULFILLED
	assert fulfilled[0].fulfilled_at is not None