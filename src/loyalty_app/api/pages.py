from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_db
from loyalty_app.config import get_settings
from loyalty_app.loyalty.qr import validate_token_shape
from loyalty_app.models import User
from loyalty_app.security import safe_next_path
from loyalty_app.templating import templates

router = APIRouter(tags=["pages"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    next_path = safe_next_path(request.query_params.get("next"))
    if request.session.get("user_id"):
        return RedirectResponse(url=next_path)
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "login.html", {"error": error, "next": next_path})


def _render_cashier_page(request: Request, session: Session, *, initial_qr_payload: str | None = None) -> Response:
    user_id = request.session.get("user_id")
    if not user_id:
        next_path = quote(str(request.url.path), safe="/")
        return RedirectResponse(url=f"/login?next={next_path}")
    user = session.get(User, user_id)
    if user is None or not user.active:
        request.session.clear()
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        request,
        "register.html",
        {"username": user.username, "role": user.role, "initial_qr_payload": initial_qr_payload},
    )


@router.get("/register", response_class=HTMLResponse)
def cashier_register_page(request: Request, session: Session = Depends(get_db)) -> Response:
    return _render_cashier_page(request, session)


@router.get("/scan/{token}", response_class=HTMLResponse)
def cashier_scan_page(token: str, request: Request, session: Session = Depends(get_db)) -> Response:
    """Entry point for 'seller scans the customer's QR with their own phone': the
    UNAS profile QR now encodes a URL of this shape (see docs/UNAS_SETUP.md and
    the profile_loyalty_qr.payload_prefix template config), so opening it lands
    here directly instead of requiring the manual scan-box text entry.

    Requires the same cashier login as every other loyalty action - if not logged
    in, this redirects to /login and back here afterwards, so the scanned token
    is never lost. The token's shape is validated by the normal resolve_scan flow
    (via the same qr.extract_token() used for manual/USB-scanner input), not here -
    an invalid token just surfaces the same generic "unknown QR code" error the
    cashier already sees for any bad scan.
    """
    settings = get_settings()
    if validate_token_shape(token, max_token_length=settings.loyalty_token_max_length) is None:
        # Still route through login if needed, but don't bother crafting a payload
        # for a token that can never resolve - the JS will just show its normal
        # focused-empty scan box.
        return _render_cashier_page(request, session)

    initial_qr_payload = str(request.url)
    return _render_cashier_page(request, session, initial_qr_payload=initial_qr_payload)


@router.get("/", response_class=HTMLResponse)
def root(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/register" if request.session.get("user_id") else "/login")
