"""Adapter that extracts the UNAS customer id from a customer_registration webhook.

Verified 2026-09-03 against a real webhook delivery (customer_registration,
sent to a live ngrok-tunneled instance from a real UNAS test shop). The actual
top-level JSON shape is:

    {
        "username": "...", "email": "...",
        "contact": {...}, "shipping": {...}, "invoice": {...},
        "customer_language": "hu", "hook_service_section": "cust",
        "shopID": "62947", "customerID": "375650086",
        "subscribedToNewsletter": false, "newsletterSubscriptionConfirmed": false,
        "language": "hu", "customerType": "private",
        "customerParameters": {"6590861": {"name": "...", "value": ""}}
    }

so the customer id lives at the top-level "customerID" key. The topic also
arrives as the "X-Unas-Topic" request header (not read here - see
api/webhook_routes.py). The extra speculative field-name candidates below are
kept as a defensive fallback in case UNAS's shape differs across shop
configurations or changes over time - if none match, the event is queued for
manual review instead of silently dropping or misinterpreting a webhook (see
docs/KNOWN_LIMITATIONS.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

_CANDIDATE_PATHS: list[tuple[str, ...]] = [
    ("customerID",),  # confirmed real UNAS field name
    ("CustomerID",),
    ("Id",),
    ("id",),
    ("CustomerId",),
    ("customerId",),
    ("customer_id",),
    ("Customer", "Id"),
    ("customer", "id"),
    ("Data", "Id"),
    ("data", "id"),
    ("Data", "CustomerId"),
    ("data", "customerId"),
]


@dataclass
class AdaptResult:
    unas_customer_id: str | None
    event_type: str | None
    matched_path: str | None


def _dig(payload: dict, path: tuple[str, ...]) -> object | None:
    node: object = payload
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def parse_customer_registration_payload(raw_body: bytes) -> AdaptResult:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return AdaptResult(unas_customer_id=None, event_type=None, matched_path=None)

    if not isinstance(payload, dict):
        return AdaptResult(unas_customer_id=None, event_type=None, matched_path=None)

    event_type = None
    for key in ("Event", "event", "EventType", "event_type", "Type", "type"):
        value = payload.get(key)
        if isinstance(value, str):
            event_type = value
            break

    for path in _CANDIDATE_PATHS:
        value = _dig(payload, path)
        if value is None:
            continue
        candidate = str(value).strip()
        if candidate and candidate.isdigit():
            return AdaptResult(unas_customer_id=candidate, event_type=event_type, matched_path=".".join(path))

    return AdaptResult(unas_customer_id=None, event_type=event_type, matched_path=None)


def mask_payload_for_logging(raw_body: bytes, max_len: int = 2000) -> str:
    """Best-effort PII-light representation kept for adapter debugging only.

    Truncates aggressively and never logged through normal application logs (see
    security.RedactingFilter) - only stored in webhook_events for admin review.
    """
    try:
        text = raw_body.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        return "<unreadable payload>"
    if len(text) > max_len:
        text = text[:max_len] + "...(truncated)"
    return text
