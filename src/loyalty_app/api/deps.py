from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from loyalty_app.db import SessionLocal
from loyalty_app.models import User
from loyalty_app.unas.client import UnasClient


def get_db(request: Request) -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_unas_client(request: Request) -> UnasClient:
    return request.app.state.unas_client


def get_current_user(request: Request, session: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Bejelentkezes szukseges")
    user = session.get(User, user_id)
    if user is None or not user.active:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Bejelentkezes szukseges")
    return user


def require_role(*roles: str):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Nincs jogosultsagod ehhez a muvelethez")
        return user

    return _check


def verify_same_origin(request: Request) -> None:
    """Pragmatic MVP CSRF mitigation for the JSON API: require the custom header a
    plain cross-site HTML form cannot attach, and if an Origin header is present,
    require it to match the Host this request actually arrived on.

    Deliberately compares against the request's own Host header rather than the
    configured APP_BASE_URL: the two can legitimately differ (accessed via
    127.0.0.1 vs localhost, behind a reverse proxy, IP vs domain, etc.), and a
    mismatch there would incorrectly reject every real request. Comparing against
    the request's own host still rejects genuine cross-origin calls. See
    docs/ARCHITECTURE_DECISIONS.md.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Ervenytelen kereles")
    origin = request.headers.get("origin")
    if origin is None:
        return
    origin_host = origin.split("://", 1)[-1].rstrip("/")
    request_host = request.headers.get("host", "")
    if origin_host != request_host:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Ervenytelen eredet (origin)")
