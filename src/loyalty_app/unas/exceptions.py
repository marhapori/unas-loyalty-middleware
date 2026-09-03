from __future__ import annotations


class UnasApiError(RuntimeError):
    """Raised for any non-transient UNAS API failure (business/validation errors,
    malformed responses, HTTP errors after retries exhausted)."""


class UnasAuthError(UnasApiError):
    """Raised when login fails or an authenticated call keeps failing auth after
    one token refresh + retry."""


class UnasTransientError(UnasApiError):
    """Network/timeout/5xx error that MAY be safe to retry for read-only calls.

    Never treated as retryable for balance-writing calls by the caller - see
    loyalty_app.loyalty.service, which explicitly does not retry set_customer_balance.
    """
