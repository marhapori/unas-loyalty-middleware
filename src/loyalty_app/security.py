from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets

import bcrypt

TOKEN_PREFIX = "L1_"


def generate_loyalty_token() -> str:
    """Cryptographically secure opaque token, >=128 bits of entropy.

    Contains no PII, no raw UNAS id, no incrementing sequence - see
    CLAUDE_CODE_UNAS_QR_MIDDLEWARE_SPEC.md section "QR-token letrehozasa".
    """
    random_part = secrets.token_urlsafe(16)  # 16 bytes = 128 bits
    return f"{TOKEN_PREFIX}{random_part}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mask_token(token: str, visible: int = 6) -> str:
    if len(token) <= visible:
        return "…" + token
    return "…" + token[-visible:]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def verify_unas_webhook(raw_body: bytes, received_signature: str, secret: str) -> bool:
    """HMAC-SHA256 over the raw body, base64-encoded, constant-time compared.

    Mirrors UNAS_API_gyakorlati_utmutato.md section 12 exactly.
    """
    if not received_signature or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, received_signature)


def webhook_event_key(raw_body: bytes) -> str:
    """Deterministic dedupe key for a webhook delivery (content hash)."""
    return hashlib.sha256(raw_body).hexdigest()


_SECRET_PATTERNS = ("api_key", "apikey", "authorization", "bearer", "token", "password", "hmac", "secret")


class RedactingFilter(logging.Filter):
    """Best-effort log filter that masks values of keys that look like secrets.

    Applied as a safety net in addition to callers simply not logging secrets in
    the first place (see UNAS_API_gyakorlati_utmutato.md section 10).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        lowered = msg.lower()
        if any(pat in lowered for pat in _SECRET_PATTERNS):
            record.msg = _redact_text(msg)
            record.args = ()
        return True


def _redact_text(text: str) -> str:
    return "[log line redacted: contained a secret-like keyword]"
