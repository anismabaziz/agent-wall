"""Sliding-window rate limiting keyed by subject (or any key)."""
import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
	"""Fixed sliding-window limiter: at most `limit` requests per `window_seconds` per key."""

	def __init__(self, limit: int, window_seconds: int = 60) -> None:
		self.limit = limit
		self.window_seconds = window_seconds
		self._timestamps: dict[str, deque] = {}
		self._lock = threading.Lock()

	def allow(self, key: str) -> bool:
		"""Record a request for `key`; return True if within quota, False if limited."""
		now = time.monotonic()
		with self._lock:
			dq = self._timestamps.setdefault(key, deque())
			while dq and now - dq[0] >= self.window_seconds:
				dq.popleft()
			if len(dq) >= self.limit:
				return False
			dq.append(now)
			return True