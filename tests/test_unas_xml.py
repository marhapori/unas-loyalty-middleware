import pytest

from loyalty_app.unas.exceptions import UnasApiError
from loyalty_app.unas.xml_utils import (
    build_get_customer_request,
    build_login_request,
    build_set_customer_balance_request,
    build_set_customer_param_request,
    parse_customers_response,
    parse_login_response,
    parse_set_customer_response,
    parse_root,
    assert_set_customer_ok,
)


def test_build_login_request_escapes_special_characters():
    xml = build_login_request("k&y<with>chars")
    assert b"&amp;" in xml
    assert b"&lt;" in xml


def test_parse_login_response_success():
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Login>
        <Token>abc123</Token>
        <Expire>2026.09.03 12:00:00</Expire>
        <ExpireTime>1893456000</ExpireTime>
        <ShopId>shop1</ShopId>
        <Subscription>VIP</Subscription>
        <Permissions>
            <Permission>getCustomer</Permission>
            <Permission>setCustomer</Permission>
        </Permissions>
        <Status>ok</Status>
    </Login>"""
    result = parse_login_response(raw)
    assert result.token == "abc123"
    assert result.expire_time == 1893456000
    assert result.shop_id == "shop1"
    assert result.subscription == "VIP"
    assert result.permissions == ["getCustomer", "setCustomer"]


def test_parse_root_raises_on_error_response():
    raw = b'<?xml version="1.0" encoding="UTF-8"?><Error>Invalid API key</Error>'
    with pytest.raises(UnasApiError, match="Invalid API key"):
        parse_root(raw)


def test_parse_root_raises_on_malformed_xml():
    with pytest.raises(UnasApiError):
        parse_root(b"not xml at all <<<")


def test_parse_customers_response_extracts_fields_and_params():
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Customers>
        <Customer>
            <Id>41704472</Id>
            <Email>gipsz.jakab@example.com</Email>
            <Contact><Name>Gipsz Jakab</Name></Contact>
            <PointsAccount><Balance>1572</Balance></PointsAccount>
            <Params>
                <Param><Id>6590861</Id><Name>Loyalty token</Name><Value>L1_abc</Value></Param>
            </Params>
        </Customer>
    </Customers>"""
    records = parse_customers_response(raw)
    assert len(records) == 1
    record = records[0]
    assert record.unas_id == "41704472"
    assert record.display_name == "Gipsz Jakab"
    assert record.points_balance == 1572.0
    assert record.params["6590861"] == "L1_abc"


def test_parse_customers_response_handles_empty_list():
    raw = b'<?xml version="1.0" encoding="UTF-8"?><Customers></Customers>'
    assert parse_customers_response(raw) == []


def test_parse_customers_response_handles_multiple_customers():
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Customers>
        <Customer><Id>1</Id></Customer>
        <Customer><Id>2</Id></Customer>
    </Customers>"""
    records = parse_customers_response(raw)
    assert [r.unas_id for r in records] == ["1", "2"]


def test_build_set_customer_param_request_uses_modify_action_and_cdata_safe_value():
    xml = build_set_customer_param_request("41704472", "6590861", "L1_<tricky>&value")
    text = xml.decode("utf-8")
    assert "<Action>modify</Action>" in text
    assert "<Id>41704472</Id>" in text
    assert "&lt;tricky&gt;" in text  # ElementTree auto-escapes, no manual CDATA needed


def test_build_set_customer_balance_request_shape():
    xml = build_set_customer_balance_request("41704472", 3520)
    text = xml.decode("utf-8")
    assert "<PointsAccount><Balance>3520</Balance></PointsAccount>" in text


def test_parse_set_customer_response_ok():
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Customers><Customer><Email>x@example.com</Email><Action>modify</Action><Id>41704472</Id><Status>ok</Status></Customer></Customers>"""
    results = parse_set_customer_response(raw)
    assert results[0].unas_id == "41704472"
    assert results[0].status == "ok"
    assert_set_customer_ok(results)  # does not raise


def test_assert_set_customer_ok_raises_on_non_ok_status():
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Customers><Customer><Id>1</Id><Status>error</Status></Customer></Customers>"""
    results = parse_set_customer_response(raw)
    with pytest.raises(UnasApiError):
        assert_set_customer_ok(results)


def test_assert_set_customer_ok_raises_on_empty_results():
    with pytest.raises(UnasApiError):
        assert_set_customer_ok([])


def test_build_get_customer_request_only_includes_provided_filters():
    xml = build_get_customer_request(id="123")
    text = xml.decode("utf-8")
    assert "<Id>123</Id>" in text
    assert "Email" not in text
    assert "LimitNum" not in text


def test_xml_roundtrip_preserves_hungarian_accents():
    xml = build_set_customer_param_request("1", "1000", "Árvíztűrő tükörfúrógép")
    parsed = parse_root(xml)
    # round-trip through our own parser to make sure the accents survive
    value = parsed.find("./Customer/Params/Param/Value").text
    assert value == "Árvíztűrő tükörfúrógép"
