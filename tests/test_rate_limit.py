"""Tests for the sliding-window rate limiter (issue #10)."""
from unittest import mock

from src.rate_limit import SlidingWindowRateLimiter


def test_allows_up_to_limit():
	limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
	assert [limiter.allow("alice") for _ in range(3)] == [True, True, True]
	assert limiter.allow("alice") is False


def test_keys_are_independent():
	limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
	assert limiter.allow("alice") is True
	assert limiter.allow("bob") is True
	assert limiter.allow("alice") is False


def test_window_resets():
	limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
	with mock.patch("time.monotonic", return_value=0.0):
		assert limiter.allow("alice") is True
		assert limiter.allow("alice") is False
	with mock.patch("time.monotonic", return_value=61.0):
		assert limiter.allow("alice") is True