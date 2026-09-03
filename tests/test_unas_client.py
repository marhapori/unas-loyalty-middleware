import httpx
import pytest
import respx

from loyalty_app.unas.client import UnasClient
from loyalty_app.unas.exceptions import UnasApiError

BASE_URL = "https://api.unas.eu/shop"

LOGIN_XML_OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<Login>
    <Token>tok-abc</Token>
    <ExpireTime>9999999999</ExpireTime>
    <ShopId>shop1</ShopId>
    <Subscription>VIP</Subscription>
    <Permissions><Permission>getCustomer</Permission><Permission>setCustomer</Permission></Permissions>
    <Status>ok</Status>
</Login>"""

CUSTOMER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Customers>
    <Customer>
        <Id>41704472</Id>
        <Contact><Name>Teszt Elek</Name></Contact>
        <PointsAccount><Balance>1572</Balance></PointsAccount>
        <Params><Param><Id>6590861</Id><Value>L1_abc</Value></Param></Params>
    </Customer>
</Customers>"""

ERROR_XML = b'<?xml version="1.0" encoding="UTF-8"?><Error>Invalid API key</Error>'


@pytest.mark.asyncio
async def test_get_customer_by_id_logs_in_once_then_reuses_token():
    with respx.mock(base_url=BASE_URL) as mock:
        login_route = mock.post("/login").mock(return_value=httpx.Response(200, content=LOGIN_XML_OK))
        mock.post("/getCustomer").mock(return_value=httpx.Response(200, content=CUSTOMER_XML))

        client = UnasClient(api_key="key123", base_url=BASE_URL)
        try:
            first = await client.get_customer_by_id("41704472")
            second = await client.get_customer_by_id("41704472")
        finally:
            await client.aclose()

        assert first.display_name == "Teszt Elek"
        assert first.points_balance == 1572.0
        assert second.unas_id == "41704472"
        assert login_route.call_count == 1  # token was cached and reused


@pytest.mark.asyncio
async def test_login_failure_raises_unas_api_error():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/login").mock(return_value=httpx.Response(400, content=ERROR_XML))

        client = UnasClient(api_key="bad-key", base_url=BASE_URL)
        try:
            with pytest.raises(UnasApiError, match="Invalid API key"):
                await client.get_customer_by_id("41704472")
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_set_customer_balance_sends_expected_body_and_parses_ok_status():
    set_customer_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Customers><Customer><Id>41704472</Id><Status>ok</Status></Customer></Customers>"""

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/login").mock(return_value=httpx.Response(200, content=LOGIN_XML_OK))
        set_route = mock.post("/setCustomer").mock(return_value=httpx.Response(200, content=set_customer_xml))

        client = UnasClient(api_key="key123", base_url=BASE_URL)
        try:
            await client.set_customer_balance("41704472", 1600)
        finally:
            await client.aclose()

        assert set_route.call_count == 1
        sent_body = set_route.calls.last.request.content
        assert b"<Balance>1600</Balance>" in sent_body


@pytest.mark.asyncio
async def test_transient_server_error_is_retried_then_succeeds():
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/login").mock(return_value=httpx.Response(200, content=LOGIN_XML_OK))
        mock.post("/getCustomer").mock(
            side_effect=[httpx.Response(503), httpx.Response(200, content=CUSTOMER_XML)]
        )

        client = UnasClient(api_key="key123", base_url=BASE_URL)
        try:
            result = await client.get_customer_by_id("41704472")
        finally:
            await client.aclose()

        assert result.unas_id == "41704472"
