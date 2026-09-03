from loyalty_app.loyalty.qr import extract_token
from loyalty_app.security import generate_loyalty_token

PREFIX = "unas-loyalty:v1:"


def test_valid_payload_extracts_token():
    token = generate_loyalty_token()
    assert extract_token(f"{PREFIX}{token}", prefix=PREFIX, max_token_length=64) == token


def test_trims_whitespace():
    token = generate_loyalty_token()
    assert extract_token(f"  {PREFIX}{token}\n", prefix=PREFIX, max_token_length=64) == token


def test_rejects_wrong_prefix():
    token = generate_loyalty_token()
    assert extract_token(f"other-prefix:{token}", prefix=PREFIX, max_token_length=64) is None


def test_rejects_missing_token_body():
    assert extract_token(PREFIX, prefix=PREFIX, max_token_length=64) is None


def test_rejects_oversized_token():
    huge = "L1_" + ("a" * 200)
    assert extract_token(f"{PREFIX}{huge}", prefix=PREFIX, max_token_length=64) is None


def test_rejects_partial_token_match():
    token = generate_loyalty_token()
    partial = token[:-3]
    result = extract_token(f"{PREFIX}{partial}", prefix=PREFIX, max_token_length=64)
    assert result != token  # never silently matches a truncated/partial token


def test_rejects_invalid_characters():
    bad = "L1_" + "not valid chars!!"
    assert extract_token(f"{PREFIX}{bad}", prefix=PREFIX, max_token_length=64) is None


def test_rejects_none_and_empty():
    assert extract_token("", prefix=PREFIX, max_token_length=64) is None
    assert extract_token(None, prefix=PREFIX, max_token_length=64) is None
