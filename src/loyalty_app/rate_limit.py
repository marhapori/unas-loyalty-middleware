from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    """Minimal in-memory sliding-window limiter, per (bucket, key).

    Adequate for a single-process, small-scale deployment (see
    docs/ARCHITECTURE_DECISIONS.md). Not shared across multiple app instances.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, bucket: str, key: str) -> None:
        now = time.monotonic()
        window = self._hits[(bucket, key)]
        while window and now - window[0] > self.window_seconds:
            window.popleft()
        if len(window) >= self.max_requests:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Tul sok kereles, probald ujra kesobb")
        window.append(now)


scan_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)
login_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
webhook_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60)
admin_bootstrap_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
