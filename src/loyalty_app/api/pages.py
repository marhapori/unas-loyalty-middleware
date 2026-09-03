from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_db
from loyalty_app.models import User
from loyalty_app.templating import templates

router = APIRouter(tags=["pages"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if request.session.get("user_id"):
        return RedirectResponse(url="/register")
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.get("/register", response_class=HTMLResponse)
def cashier_register_page(request: Request, session: Session = Depends(get_db)) -> Response:
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")
    user = session.get(User, user_id)
    if user is None or not user.active:
        request.session.clear()
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "register.html", {"username": user.username, "role": user.role})


@router.get("/", response_class=HTMLResponse)
def root(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/register" if request.session.get("user_id") else "/login")
