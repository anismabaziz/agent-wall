"""Tests for the command-line interface (issue #13)."""
import json
import os
import tempfile

# Route the shared SQLAlchemy engine to a temp DB and wipe it between tests so
# CLI runs don't accumulate records across tests.
os.environ["AGENT_WALL_AUDIT_DB"] = os.path.join(
	tempfile.gettempdir(), "aw_cli_test.db"
)

import pytest

from src.db import Base, Session, engine as shared_engine

from src.cli import main  # noqa: E402

POLICY = "policies/p5_composite.yaml"


@pytest.fixture(autouse=True)
def _fresh_tables():
	Base.metadata.drop_all(bind=shared_engine)
	Base.metadata.create_all(bind=shared_engine)
	yield


def test_check_valid_policy(capsys):
	assert main(["check", "--policy", POLICY]) == 0
	out = capsys.readouterr().out
	assert "OK:" in out
	assert "permissions" in out


def test_check_invalid_policy(capsys):
	assert main(["check", "--policy", "policies/does_not_exist.yaml"]) == 1
	assert "INVALID:" in capsys.readouterr().out


def test_evaluate_permit_returns_verdict(capsys):
	code = main([
		"evaluate",
		"--policy", POLICY,
		"--subject", "pay_agent_1",
		"--action", "execute_payment",
		"--resource", "tx://hvc",
		"--context", "is_high_value=true",
		"--context", "has_treasury_approval=true",
	])
	assert code == 0
	data = json.loads(capsys.readouterr().out)
	assert data["decision"] == "PERMIT"
	assert "Ob_FileCTR" in data["obligations"]


def test_evaluate_prohibit(capsys):
	code = main([
		"evaluate",
		"--policy", POLICY,
		"--subject", "pay_agent_1",
		"--action", "execute_payment",
		"--context", "is_high_value=true",
	])
	assert code == 0
	data = json.loads(capsys.readouterr().out)
	assert data["decision"] == "PROHIBIT"


def test_obligations_lists_persisted_record(capsys):
	main([
		"evaluate",
		"--policy", POLICY,
		"--subject", "pay_agent_1",
		"--action", "execute_payment",
		"--resource", "tx://hvc",
		"--context", "is_high_value=true",
		"--context", "has_treasury_approval=true",
	])
	capsys.readouterr()

	assert main(["obligations"]) == 0
	records = json.loads(capsys.readouterr().out)
	assert len(records) == 1
	assert records[0]["obligation_id"] == "Ob_FileCTR"
	assert records[0]["permission_id"] == "Perm_ApprovedHighValue"
	assert records[0]["status"] == "PENDING"


def test_audit_log_after_evaluate(capsys):
	main([
		"evaluate",
		"--policy", POLICY,
		"--subject", "pay_agent_1",
		"--action", "execute_payment",
		"--context", "is_high_value=true",
		"--context", "has_treasury_approval=true",
	])
	capsys.readouterr()

	assert main(["audit-log", "--limit", "10"]) == 0
	rows = json.loads(capsys.readouterr().out)
	assert any(r["verdict"] == "PERMIT" for r in rows)