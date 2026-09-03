from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_current_user, get_db, get_unas_client, verify_same_origin
from loyalty_app.api.schemas import ScanCustomer, ScanRequest, ScanResponse
from loyalty_app.config import Settings, get_settings
from loyalty_app.loyalty import service
from loyalty_app.loyalty.errors import CustomerNotFound
from loyalty_app.models import User
from loyalty_app.rate_limit import scan_limiter
from loyalty_app.unas.client import UnasClient
from loyalty_app.unas.exceptions import UnasApiError

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("/resolve", response_model=ScanResponse, dependencies=[Depends(verify_same_origin)])
async def resolve_scan(
    request: Request,
    body: ScanRequest,
    session: Session = Depends(get_db),
    unas_client: UnasClient = Depends(get_unas_client),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(get_current_user),
) -> ScanResponse:
    scan_limiter.check("scan", request.client.host if request.client else "unknown")
    try:
        result = await service.resolve_scan(session, unas_client, settings, body.qrPayload)
    except CustomerNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ismeretlen vagy ervenytelen QR-kod") from None
    except UnasApiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"UNAS kapcsolati hiba: {exc}") from exc

    return ScanResponse(
        customer=ScanCustomer(displayName=result.display_name, maskedCardId=result.masked_token),
        pointsBalance=str(result.points_balance),
    )
