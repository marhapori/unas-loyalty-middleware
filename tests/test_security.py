import base64
import hashlib
import hmac

from loyalty_app.security import (
    generate_loyalty_token,
    hash_password,
    hash_token,
    mask_token,
    safe_next_path,
    verify_password,
    verify_unas_webhook,
    webhook_event_key,
)


def test_generate_loyalty_token_shape_and_uniqueness():
    tokens = {generate_loyalty_token() for _ in range(200)}
    assert len(tokens) == 200  # no collisions
    for token in tokens:
        assert token.startswith("L1_")
        assert len(token) > 15


def test_hash_token_is_deterministic_sha256():
    token = "L1_example"
    assert hash_token(token) == hashlib.sha256(token.encode("utf-8")).hexdigest()


def test_mask_token_hides_all_but_suffix():
    masked = mask_token("L1_abcdefghijklmnop")
    assert masked.endswith("klmnop")
    assert "L1_" not in masked


def test_password_hash_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_verify_unas_webhook_matches_reference_php_algorithm():
    secret = "hmac_secret"
    body = b'{"Event":"customer_registration","Id":123}'
    signature = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode()
    assert verify_unas_webhook(body, signature, secret)


def test_verify_unas_webhook_rejects_tampered_body():
    secret = "hmac_secret"
    body = b'{"Id":123}'
    signature = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode()
    assert not verify_unas_webhook(b'{"Id":124}', signature, secret)


def test_verify_unas_webhook_rejects_missing_signature_or_secret():
    assert not verify_unas_webhook(b"body", "", "secret")
    assert not verify_unas_webhook(b"body", "sig", "")


def test_webhook_event_key_is_deterministic():
    body = b"same body"
    assert webhook_event_key(body) == webhook_event_key(body)
    assert webhook_event_key(b"a") != webhook_event_key(b"b")


def test_safe_next_path_accepts_relative_paths():
    assert safe_next_path("/scan/L1_abc") == "/scan/L1_abc"


def test_safe_next_path_rejects_external_urls():
    assert safe_next_path("https://evil.example.com/phish") == "/register"


def test_safe_next_path_rejects_protocol_relative_urls():
    assert safe_next_path("//evil.example.com") == "/register"


def test_safe_next_path_rejects_scheme_embedded_in_path():
    assert safe_next_path("/redirect?to=https://evil.example.com") == "/register"


def test_safe_next_path_defaults_on_missing_value():
    assert safe_next_path(None) == "/register"
    assert safe_next_path("") == "/register"
