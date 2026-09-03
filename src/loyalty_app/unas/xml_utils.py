"""XML request builders / response parsers for the UNAS Shop API.

Field names verified 2026-09-03 against the live UNAS API documentation
(https://unas.hu/tudastar/api/...) for login, getCustomer/setCustomer and the
customer data structure. The one unverified assumption is that the getCustomer
*request* root element is ``<Params>`` (consistent with every other UNAS GET
endpoint shown in the docs, e.g. getProduct/getOrder) - the getCustomer request
page lists the filter fields but does not show a full example XML. Confirm this
with a real API key (a single ``getCustomer`` call by Id) before relying on
filtered/paged customer listing in production; see docs/KNOWN_LIMITATIONS.md.

Building always goes through ``xml.etree.ElementTree`` (never string
concatenation), which escapes special characters automatically. Parsing always
goes through ``defusedxml.ElementTree``, which disables external entity
resolution (XXE protection), per the security requirements in both spec docs.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import defusedxml.ElementTree as DET

from loyalty_app.unas.exceptions import UnasApiError


def _serialize(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def _add(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = text
    return el


def parse_root(raw_xml: bytes) -> ET.Element:
    try:
        root = DET.fromstring(raw_xml)
    except DET.ParseError as exc:
        raise UnasApiError(f"Nem ertelmezheto XML valasz erkezett a UNAS API-tol: {exc}") from exc
    if root.tag == "Error":
        raise UnasApiError((root.text or "Ismeretlen UNAS API hiba").strip())
    return root


# --- login -------------------------------------------------------------


def build_login_request(api_key: str) -> bytes:
    root = ET.Element("Params")
    _add(root, "ApiKey", api_key)
    return _serialize(root)


@dataclass
class LoginResult:
    token: str
    expire_time: int
    shop_id: str | None
    subscription: str | None
    permissions: list[str] = field(default_factory=list)


def parse_login_response(raw_xml: bytes) -> LoginResult:
    root = parse_root(raw_xml)
    token = root.findtext("Token")
    expire_time = root.findtext("ExpireTime")
    if not token or not expire_time:
        raise UnasApiError("A login valaszbol hianyzik a Token vagy az ExpireTime mezo")
    permissions = [
        (p.text or "").strip()
        for p in root.findall("./Permissions/Permission")
        if (p.text or "").strip()
    ]
    return LoginResult(
        token=token,
        expire_time=int(expire_time),
        shop_id=root.findtext("ShopId"),
        subscription=root.findtext("Subscription"),
        permissions=permissions,
    )


# --- getCustomer ---------------------------------------------------------


def build_get_customer_request(
    *,
    id: str | None = None,
    email: str | None = None,
    reg_time_start: int | None = None,
    reg_time_end: int | None = None,
    mod_time_start: int | None = None,
    mod_time_end: int | None = None,
    limit_start: int | None = None,
    limit_num: int | None = None,
) -> bytes:
    root = ET.Element("Params")
    if id is not None:
        _add(root, "Id", str(id))
    if email is not None:
        _add(root, "Email", email)
    if reg_time_start is not None:
        _add(root, "RegTimeStart", str(reg_time_start))
    if reg_time_end is not None:
        _add(root, "RegTimeEnd", str(reg_time_end))
    if mod_time_start is not None:
        _add(root, "ModTimeStart", str(mod_time_start))
    if mod_time_end is not None:
        _add(root, "ModTimeEnd", str(mod_time_end))
    if limit_start is not None:
        _add(root, "LimitStart", str(limit_start))
    if limit_num is not None:
        _add(root, "LimitNum", str(limit_num))
    return _serialize(root)


@dataclass
class CustomerRecord:
    unas_id: str
    email: str | None
    display_name: str | None
    points_balance: float | None
    params: dict[str, str]


def _customer_display_name(customer_el: ET.Element) -> str | None:
    name = customer_el.findtext("./Contact/Name")
    if name and name.strip():
        return name.strip()
    name = customer_el.findtext("./Addresses/Invoice/Name")
    if name and name.strip():
        return name.strip()
    return None


def parse_customers_response(raw_xml: bytes) -> list[CustomerRecord]:
    root = parse_root(raw_xml)
    records: list[CustomerRecord] = []
    for customer_el in root.findall("./Customer"):
        unas_id = customer_el.findtext("Id")
        if not unas_id:
            continue
        balance_text = customer_el.findtext("./PointsAccount/Balance")
        params: dict[str, str] = {}
        for param_el in customer_el.findall("./Params/Param"):
            param_id = param_el.findtext("Id")
            if param_id:
                params[param_id] = (param_el.findtext("Value") or "").strip()
        records.append(
            CustomerRecord(
                unas_id=unas_id,
                email=customer_el.findtext("Email"),
                display_name=_customer_display_name(customer_el),
                points_balance=float(balance_text) if balance_text not in (None, "") else None,
                params=params,
            )
        )
    return records


# --- setCustomer ---------------------------------------------------------


def build_set_customer_param_request(unas_id: str, param_id: str, value: str) -> bytes:
    root = ET.Element("Customers")
    customer = ET.SubElement(root, "Customer")
    _add(customer, "Action", "modify")
    _add(customer, "Id", str(unas_id))
    params = ET.SubElement(customer, "Params")
    param = ET.SubElement(params, "Param")
    _add(param, "Id", str(param_id))
    _add(param, "Value", value)
    return _serialize(root)


def build_set_customer_balance_request(unas_id: str, new_balance: int) -> bytes:
    root = ET.Element("Customers")
    customer = ET.SubElement(root, "Customer")
    _add(customer, "Action", "modify")
    _add(customer, "Id", str(unas_id))
    points_account = ET.SubElement(customer, "PointsAccount")
    _add(points_account, "Balance", str(new_balance))
    return _serialize(root)


@dataclass
class SetCustomerResult:
    unas_id: str
    status: str


def parse_set_customer_response(raw_xml: bytes) -> list[SetCustomerResult]:
    root = parse_root(raw_xml)
    results: list[SetCustomerResult] = []
    for customer_el in root.findall("./Customer"):
        results.append(
            SetCustomerResult(
                unas_id=customer_el.findtext("Id") or "",
                status=(customer_el.findtext("Status") or "").strip().lower(),
            )
        )
    return results


def assert_set_customer_ok(results: list[SetCustomerResult]) -> None:
    if not results:
        raise UnasApiError("A setCustomer valasz nem tartalmazott egyetlen vasarlo eredmenyt sem")
    for result in results:
        if result.status != "ok":
            raise UnasApiError(f"setCustomer sikertelen a(z) {result.unas_id} vasarlonal (status={result.status})")
