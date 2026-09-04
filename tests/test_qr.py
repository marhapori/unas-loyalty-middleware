from loyalty_app.loyalty.qr import extract_token, validate_token_shape
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


# --- URL-shaped payload (seller scans the customer's QR with their own phone,
# which now encodes a URL - see docs/ARCHITECTURE_DECISIONS.md) -----------------


def test_extracts_token_from_scan_url():
    token = generate_loyalty_token()
    url = f"https://example.com/scan/{token}"
    assert extract_token(url, prefix=PREFIX, max_token_length=64) == token


def test_extracts_token_from_scan_url_with_trailing_slash():
    token = generate_loyalty_token()
    url = f"https://example.com/scan/{token}/"
    assert extract_token(url, prefix=PREFIX, max_token_length=64) == token


def test_extracts_token_from_scan_url_with_query_string():
    token = generate_loyalty_token()
    url = f"https://example.com/scan/{token}?utm_source=qr"
    assert extract_token(url, prefix=PREFIX, max_token_length=64) == token


def test_rejects_url_with_invalid_token_segment():
    url = "https://example.com/scan/not-a-real-token"
    assert extract_token(url, prefix=PREFIX, max_token_length=64) is None


def test_rejects_url_without_path():
    assert extract_token("https://example.com", prefix=PREFIX, max_token_length=64) is None


def test_rejects_plain_scheme_without_recognizable_envelope():
    # ftp:// etc. must not be treated as a URL envelope
    token = generate_loyalty_token()
    assert extract_token(f"ftp://example.com/scan/{token}", prefix=PREFIX, max_token_length=64) is None


# --- validate_token_shape (used directly by the /scan/{token} route) -----------


def test_validate_token_shape_accepts_valid_token():
    token = generate_loyalty_token()
    assert validate_token_shape(token, max_token_length=64) == token


def test_validate_token_shape_rejects_missing_prefix():
    assert validate_token_shape("not-our-format", max_token_length=64) is None


def test_validate_token_shape_rejects_none_and_empty():
    assert validate_token_shape(None, max_token_length=64) is None
    assert validate_token_shape("", max_token_length=64) is None
