"""Temporary, token-gated admin bootstrap endpoint.

Only needed because some free-tier hosting platforms (e.g. Render's free Web
Service plan) give no Shell/SSH access to the running instance, so the normal
`seed-store` / `create-user` CLI commands (cli.py) can't be run against the
deployed database directly. This endpoint does the exact same two operations
over HTTP instead, gated by a separate secret (ADMIN_BOOTSTRAP_TOKEN) that is
empty by default - fail-closed: with no token configured, this route always
refuses. Once initial setup is done, unset ADMIN_BOOTSTRAP_TOKEN in the hosting
platform's environment variables to close it off again.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_db
from loyalty_app.api.schemas import AdminBootstrapRequest, AdminBootstrapResponse
from loyalty_app.config import Settings, get_settings
from loyalty_app.models import Store, User
from loyalty_app.rate_limit import admin_bootstrap_limiter
from loyalty_app.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/bootstrap", response_model=AdminBootstrapResponse)
def bootstrap(
    request: Request,
    body: AdminBootstrapRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminBootstrapResponse:
    admin_bootstrap_limiter.check("admin_bootstrap", request.client.host if request.client else "unknown")

    if not settings.admin_bootstrap_token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")

    provided = request.headers.get("x-bootstrap-token", "")
    if not hmac.compare_digest(provided, settings.admin_bootstrap_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Ervenytelen bootstrap token")

    store = session.execute(select(Store).where(Store.code == body.storeCode)).scalar_one_or_none()
    store_created = False
    if store is None:
        store = Store(name=body.storeName, code=body.storeCode)
        session.add(store)
        session.flush()
        store_created = True

    user = session.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    user_created = False
    if user is None:
        user = User(
            username=body.username,
            password_hash=hash_password(body.password),
            role=body.role,
            store_id=store.id,
        )
        session.add(user)
        user_created = True

    session.commit()
    return AdminBootstrapResponse(storeCreated=store_created, userCreated=user_created)
