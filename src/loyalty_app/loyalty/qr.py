from __future__ import annotations

import re

from loyalty_app.security import TOKEN_PREFIX

# base64url alphabet used by secrets.token_urlsafe, plus our fixed "L1_" prefix.
_TOKEN_BODY_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")


def extract_token(raw_payload: str, *, prefix: str, max_token_length: int) -> str | None:
    """Validate a scanned QR payload and return the bare token, or None if invalid.

    Deliberately strict and exact-match only (never partial/prefix DB lookups):
    - must start with the configured prefix exactly
    - the remaining token must match our known generated shape
    - length is bounded to avoid abuse via oversized input
    An invalid payload must never reveal whether a customer exists - callers should
    return the same generic "not found" response for a malformed payload and for a
    well-formed-but-unknown token.
    """
    if raw_payload is None:
        return None
    payload = raw_payload.strip()
    if not payload.startswith(prefix):
        return None
    token = payload[len(prefix):]
    if not token or len(token) > max_token_length:
        return None
    if not token.startswith(TOKEN_PREFIX):
        return None
    body = token[len(TOKEN_PREFIX):]
    if not _TOKEN_BODY_RE.match(body):
        return None
    return token
