"""A fake, in-memory stand-in for UnasClient used by service/route-level tests.

Duck-types the subset of UnasClient's public async interface that
loyalty_app.loyalty.service and loyalty_app.worker actually call, so tests never
touch the network. Failure injection lets tests exercise the transient-error and
hard-failure branches of the service layer.
"""

from __future__ import annotations

import asyncio

from loyalty_app.unas.exceptions import UnasApiError, UnasTransientError
from loyalty_app.unas.xml_utils import CustomerRecord

# A tiny real await point so concurrent callers (asyncio.gather in tests) actually
# interleave at this point instead of running each coroutine to completion in one
# go - this is what makes loyalty_app.concurrency.customer_locks-dependent tests
# meaningful (they would fail without the lock, given a real interleaving).
_SIMULATED_NETWORK_DELAY = 0.01


class FakeUnasCustomer:
    def __init__(self, unas_id: str, display_name: str, balance: float, params: dict[str, str] | None = None) -> None:
        self.unas_id = unas_id
        self.display_name = display_name
        self.balance = balance
        self.params = params or {}


class FakeUnasClient:
    def __init__(self) -> None:
        self.customers: dict[str, FakeUnasCustomer] = {}
        self.set_balance_calls: list[tuple[str, int]] = []
        self.set_param_calls: list[tuple[str, str, str]] = []
        self.fail_next_balance_write: Exception | None = None

    def add_customer(self, unas_id: str, display_name: str, balance: float = 0, params: dict[str, str] | None = None) -> FakeUnasCustomer:
        customer = FakeUnasCustomer(unas_id, display_name, balance, params)
        self.customers[unas_id] = customer
        return customer

    async def get_customer_by_id(self, unas_id: str) -> CustomerRecord | None:
        await asyncio.sleep(_SIMULATED_NETWORK_DELAY)
        customer = self.customers.get(unas_id)
        if customer is None:
            return None
        return CustomerRecord(
            unas_id=customer.unas_id,
            email=None,
            display_name=customer.display_name,
            points_balance=customer.balance,
            params=dict(customer.params),
        )

    async def get_customers_page(self, *, limit_start: int = 0, limit_num: int = 100, **_kw) -> list[CustomerRecord]:
        all_records = [
            CustomerRecord(unas_id=c.unas_id, email=None, display_name=c.display_name, points_balance=c.balance, params=dict(c.params))
            for c in self.customers.values()
        ]
        return all_records[limit_start : limit_start + limit_num]

    async def set_customer_param(self, unas_id: str, param_id: str, value: str) -> None:
        self.set_param_calls.append((unas_id, param_id, value))
        customer = self.customers.get(unas_id)
        if customer is None:
            raise UnasApiError(f"unknown customer {unas_id}")
        customer.params[param_id] = value

    async def set_customer_balance(self, unas_id: str, new_balance: int) -> None:
        await asyncio.sleep(_SIMULATED_NETWORK_DELAY)
        self.set_balance_calls.append((unas_id, new_balance))
        if self.fail_next_balance_write is not None:
            exc, self.fail_next_balance_write = self.fail_next_balance_write, None
            raise exc
        customer = self.customers.get(unas_id)
        if customer is None:
            raise UnasApiError(f"unknown customer {unas_id}")
        customer.balance = new_balance
