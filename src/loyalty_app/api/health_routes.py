from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(session: Session = Depends(get_db)) -> dict:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/outbound-ip")
async def outbound_ip() -> dict:
    """Temporary diagnostic: reveals this instance's outbound IP address, for
    reporting to UNAS support while investigating a suspected IP-based block
    (see docs/KNOWN_LIMITATIONS.md, 2026-09-04/05). No secrets involved - safe
    to leave public. Remove once the connectivity issue is resolved."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get("https://api.ipify.org?format=json")
        return response.json()
