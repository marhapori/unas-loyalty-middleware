from __future__ import annotations

import re

from loyalty_app.security import TOKEN_PREFIX

# base64url alphabet used by secrets.token_urlsafe, plus our fixed "L1_" prefix.
_TOKEN_BODY_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")


def validate_token_shape(candidate: str | None, *, max_token_length: int) -> str | None:
    """Validate a bare token string (no prefix/URL wrapper) and return it, or None.

    Shared by both accepted payload shapes in extract_token() below, and by the
    /scan/{token} route (api/pages.py), which already has the token isolated via
    URL path routing and just needs this shape check before trusting it.
    """
    if not candidate or len(candidate) > max_token_length:
        return None
    if not candidate.startswith(TOKEN_PREFIX):
        return None
    body = candidate[len(TOKEN_PREFIX):]
    if not _TOKEN_BODY_RE.match(body):
        return None
    return candidate


def extract_token(raw_payload: str, *, prefix: str, max_token_length: int) -> str | None:
    """Validate a scanned QR payload and return the bare token, or None if invalid.

    Two accepted shapes, both requiring some recognizable envelope (never a bare
    token typed alone, to avoid false-positive matches on arbitrary manual input):

    1. Legacy inline format: ``<prefix><token>`` (e.g. ``unas-loyalty:v1:L1_xyz``),
       as typed by a USB scanner into the manual scan box, or produced by an older
       UNAS profile-page QR template.
    2. URL format: ``https://.../scan/<token>`` (optionally with a query string or
       trailing slash) - what a phone camera opens directly when the UNAS profile
       QR now encodes a URL (see docs/ARCHITECTURE_DECISIONS.md, "eladoi telefon"
       scan flow). The token is taken as the last non-empty path segment.

    Deliberately strict and exact-match only (never partial/prefix DB lookups) -
    an invalid payload must never reveal whether a customer exists; callers should
    return the same generic "not found" response for a malformed payload and for a
    well-formed-but-unknown token.
    """
    if raw_payload is None:
        return None
    payload = raw_payload.strip()
    if not payload:
        return None

    if payload.startswith(prefix):
        return validate_token_shape(payload[len(prefix):], max_token_length=max_token_length)

    if payload.startswith("http://") or payload.startswith("https://"):
        without_query = payload.split("?", 1)[0].split("#", 1)[0]
        segments = [s for s in without_query.rstrip("/").split("/") if s]
        if segments:
            return validate_token_shape(segments[-1], max_token_length=max_token_length)

    return None
