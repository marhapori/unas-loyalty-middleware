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
    """Reveals this instance's outbound IP address - useful when reporting a
    suspected IP-based block to UNAS support (see docs/KNOWN_LIMITATIONS.md),
    or when a hosting migration needs the new IP for a whitelist request. No
    secrets involved."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get("https://api.ipify.org?format=json")
        return response.json()
