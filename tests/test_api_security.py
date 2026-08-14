"""Tests for API auth, per-subject rate limiting, and CORS (issue #10).

Pagination on /obligations is covered in test_api.py (issue #17).
"""
import os
import tempfile

# Ensure the app uses an isolated DB before importing src.api.
os.environ.setdefault("AGENT_WALL_AUDIT_DB", os.path.join(tempfile.gettempdir(), "aw_api_security.db"))

from fastapi.testclient import TestClient  # noqa: E402

import src.api as api  # noqa: E402
from src.rate_limit import SlidingWindowRateLimiter  # noqa: E402


def _client():
	return TestClient(api.app)


def test_no_auth_by_default(monkeypatch):
	monkeypatch.setattr(api, "API_KEY", None)
	client = _client()
	assert client.get("/obligations").status_code == 200


def test_missing_or_invalid_key_rejected(monkeypatch):
	monkeypatch.setattr(api, "API_KEY", "s3cret")
	client = _client()

	resp = client.get("/obligations")
	assert resp.status_code == 401

	resp = client.get("/obligations", headers={"X-API-Key": "wrong"})
	assert resp.status_code == 401

	resp = client.get("/obligations", headers={"X-API-Key": "s3cret"})
	assert resp.status_code == 200


def test_evaluate_requires_key_when_enabled(monkeypatch):
	monkeypatch.setattr(api, "API_KEY", "s3cret")
	monkeypatch.setattr(api, "RATE_LIMIT", 0)
	client = _client()

	payload = {
		"subject": "pay_agent_1",
		"action_type": "execute_payment",
		"resource": "tx://hvc",
		"context": {"is_high_value": True, "has_treasury_approval": True},
	}
	assert client.post("/evaluate", json=payload).status_code == 401
	assert client.post("/evaluate", json=payload, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_per_subject_rate_limit(monkeypatch):
	monkeypatch.setattr(api, "API_KEY", None)
	monkeypatch.setattr(api, "RATE_LIMIT", 2)
	monkeypatch.setattr(api, "_limiter", SlidingWindowRateLimiter(limit=2, window_seconds=60))
	client = _client()

	payload = {
		"subject": "pay_agent_1",
		"action_type": "execute_payment",
		"resource": "tx://hvc",
		"context": {"is_high_value": True, "has_treasury_approval": True},
	}
	assert client.post("/evaluate", json=payload).status_code == 200
	assert client.post("/evaluate", json=payload).status_code == 200
	assert client.post("/evaluate", json=payload).status_code == 429

	# checkout log: a different subject is unaffected
	other = {**payload, "subject": "other_agent"}
	assert client.post("/evaluate", json=other).status_code == 200


def test_cors_headers_present_on_origin_request():
	client = _client()
	resp = client.get("/obligations", headers={"Origin": "http://localhost:5173"})
	assert resp.headers.get("access-control-allow-origin") is not None