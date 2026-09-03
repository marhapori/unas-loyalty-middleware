from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from loyalty_app.unas.exceptions import UnasAuthError, UnasTransientError
from loyalty_app.unas.xml_utils import (
    CustomerRecord,
    LoginResult,
    build_get_customer_request,
    build_login_request,
    build_set_customer_balance_request,
    build_set_customer_param_request,
    parse_customers_response,
    parse_login_response,
    parse_set_customer_response,
    assert_set_customer_ok,
)

logger = logging.getLogger("loyalty_app.unas")

_TRANSIENT_STATUS_CODES = {502, 503, 504}


@dataclass
class _TokenState:
    value: str
    expires_at: int


class _RateLimiter:
    """Minimal async token-bucket-ish limiter: at most N requests/second."""

    def __init__(self, requests_per_second: float) -> None:
        self._min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_at = time.monotonic()


class UnasClient:
    """Thin, isolated UNAS Shop API client (XML over HTTPS, Bearer token auth).

    - login()/token cache with expiry-aware refresh (see get_token)
    - one re-login + retry on an authenticated call that fails auth
    - limited retry (tenacity) only for transient network/5xx errors, and only for
      read calls - set_customer_balance is never automatically retried, per
      UNAS_API_gyakorlati_utmutato.md section 10 ("Ne probald vakon ujra... egy
      tobbentitasos set... kerest").
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.unas.eu/shop",
        timeout_seconds: float = 30.0,
        requests_per_second: float = 5.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=timeout_seconds)
        self._token: _TokenState | None = None
        self._token_lock = asyncio.Lock()
        self._rate_limiter = _RateLimiter(requests_per_second)

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- token lifecycle ----------------------------------------------

    async def login(self) -> _TokenState:
        body = build_login_request(self.api_key)
        raw = await self._post("login", body, authenticated=False, retryable=True)
        result: LoginResult = parse_login_response(raw)
        self._token = _TokenState(value=result.token, expires_at=result.expire_time)
        logger.info("unas login ok shop_id=%s subscription=%s", result.shop_id, result.subscription)
        return self._token

    async def get_token(self) -> str:
        async with self._token_lock:
            if self._token is None or time.time() >= self._token.expires_at - 60:
                await self.login()
            assert self._token is not None
            return self._token.value

    async def invalidate_token(self) -> None:
        async with self._token_lock:
            self._token = None

    # -- customers ------------------------------------------------------

    async def get_customer_by_id(self, unas_id: str) -> CustomerRecord | None:
        records = await self._get_customers(id=unas_id)
        return records[0] if records else None

    async def get_customers_page(
        self,
        *,
        mod_time_start: int | None = None,
        reg_time_start: int | None = None,
        limit_start: int = 0,
        limit_num: int = 100,
    ) -> list[CustomerRecord]:
        return await self._get_customers(
            mod_time_start=mod_time_start,
            reg_time_start=reg_time_start,
            limit_start=limit_start,
            limit_num=limit_num,
        )

    async def _get_customers(self, **filters) -> list[CustomerRecord]:
        body = build_get_customer_request(**filters)
        raw = await self._authenticated_post("getCustomer", body, retryable=True)
        return parse_customers_response(raw)

    async def set_customer_param(self, unas_id: str, param_id: str, value: str) -> None:
        body = build_set_customer_param_request(unas_id, param_id, value)
        raw = await self._authenticated_post("setCustomer", body, retryable=False)
        assert_set_customer_ok(parse_set_customer_response(raw))

    async def set_customer_balance(self, unas_id: str, new_balance: int) -> None:
        body = build_set_customer_balance_request(unas_id, new_balance)
        raw = await self._authenticated_post("setCustomer", body, retryable=False)
        assert_set_customer_ok(parse_set_customer_response(raw))

    # -- transport --------------------------------------------------------

    async def _authenticated_post(self, function: str, body: bytes, *, retryable: bool) -> bytes:
        token = await self.get_token()
        try:
            return await self._post(function, body, authenticated=True, retryable=retryable, token=token)
        except UnasAuthError:
            await self.invalidate_token()
            token = await self.get_token()
            return await self._post(function, body, authenticated=True, retryable=retryable, token=token)

    async def _post(
        self,
        function: str,
        body: bytes,
        *,
        authenticated: bool,
        retryable: bool,
        token: str | None = None,
    ) -> bytes:
        if retryable:
            return await self._post_with_retry(function, body, authenticated=authenticated, token=token)
        return await self._post_once(function, body, authenticated=authenticated, token=token)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(UnasTransientError),
    )
    async def _post_with_retry(self, function: str, body: bytes, *, authenticated: bool, token: str | None) -> bytes:
        return await self._post_once(function, body, authenticated=authenticated, token=token)

    async def _post_once(self, function: str, body: bytes, *, authenticated: bool, token: str | None) -> bytes:
        await self._rate_limiter.wait()
        headers = {"Content-Type": "application/xml; charset=utf-8", "Accept": "application/xml"}
        if authenticated:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = await self._http.post(f"{self.base_url}/{function}", content=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise UnasTransientError(f"Halozati hiba a(z) {function} hivasnal: {exc}") from exc

        if response.status_code in _TRANSIENT_STATUS_CODES:
            raise UnasTransientError(f"UNAS {function} atmeneti szerverhiba: HTTP {response.status_code}")

        if response.status_code == 401 or response.status_code == 403:
            raise UnasAuthError(f"UNAS {function} hitelesitesi hiba: HTTP {response.status_code}")

        # Any other status (2xx success, or UNAS's typical 400 + <Error> XML for
        # general/business errors per UNAS_API_gyakorlati_utmutato.md section 10)
        # is handed to the XML parser: parse_root() raises UnasApiError with the
        # real <Error> message when present, which is far more useful than a bare
        # HTTP status code.
        return response.content
