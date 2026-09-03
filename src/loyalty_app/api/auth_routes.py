from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_db
from loyalty_app.models import User
from loyalty_app.rate_limit import login_limiter
from loyalty_app.security import verify_password

router = APIRouter(tags=["auth"])


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_db),
) -> RedirectResponse:
    login_limiter.check("login", request.client.host if request.client else "unknown")

    user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=1", status_code=303)

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    request.session["username"] = user.username
    return RedirectResponse(url="/register", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
