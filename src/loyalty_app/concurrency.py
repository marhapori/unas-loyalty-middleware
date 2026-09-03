from __future__ import annotations

import asyncio
from collections import defaultdict


class KeyedLockRegistry:
    """In-process asyncio locks keyed by an arbitrary string (e.g. customer id).

    This is the primary guard against concurrent earn/redeem/reverse operations on
    the same loyalty customer when running as a single process (the default,
    SQLite-backed deployment this app targets). It does NOT protect across multiple
    processes/workers - if the app is later scaled out behind Postgres with several
    worker processes, the ``SELECT ... FOR UPDATE`` row lock used in
    loyalty_app.loyalty.service becomes the authoritative cross-process guard
    instead. See docs/ARCHITECTURE_DECISIONS.md.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def get(self, key: str) -> asyncio.Lock:
        return self._locks[key]


customer_locks = KeyedLockRegistry()
