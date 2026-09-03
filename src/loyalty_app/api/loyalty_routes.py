from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_current_user, get_db, get_unas_client, require_role, verify_same_origin
from loyalty_app.api.schemas import (
    EarnRequest,
    LoyaltyConfigResponse,
    RedeemRequest,
    ReverseRequest,
    TransactionListItem,
    TransactionResponse,
)
from loyalty_app.config import Settings, get_settings
from loyalty_app.loyalty import service
from loyalty_app.loyalty.errors import LoyaltyServiceError
from loyalty_app.loyalty.rules import RuleViolation
from loyalty_app.models import LoyaltyTransaction, User
from loyalty_app.unas.client import UnasClient
from loyalty_app.unas.exceptions import UnasApiError

router = APIRouter(prefix="/api/loyalty", tags=["loyalty"], dependencies=[Depends(verify_same_origin)])

_ERROR_STATUS = {
    "customer_not_found": status.HTTP_404_NOT_FOUND,
    "transaction_not_found": status.HTTP_404_NOT_FOUND,
    "transaction_in_flight": status.HTTP_409_CONFLICT,
    "already_reversed": status.HTTP_409_CONFLICT,
    "not_reversible": status.HTTP_409_CONFLICT,
    "write_uncertain": status.HTTP_202_ACCEPTED,
    "unas_write_failed": status.HTTP_502_BAD_GATEWAY,
}


def _to_response(result: service.TransactionResult) -> TransactionResponse:
    return TransactionResponse(
        transactionId=result.transaction_id,
        status=result.status,
        balanceBefore=str(result.balance_before),
        balanceAfter=str(result.balance_after),
        pointsDelta=str(result.points_delta),
    )


def _raise_for(exc: Exception) -> HTTPException:
    if isinstance(exc, RuleViolation):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, LoyaltyServiceError):
        http_status = _ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST)
        return HTTPException(http_status, detail=str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"UNAS kapcsolati hiba: {exc}")


@router.get("/config", response_model=LoyaltyConfigResponse)
def loyalty_config(
    settings: Settings = Depends(get_settings), _user: User = Depends(get_current_user)
) -> LoyaltyConfigResponse:
    """Read-only echo of the active business rule config, so the cashier UI can
    show a client-side *preview* of the point delta before confirming. The server
    always recomputes the authoritative value on submit - see loyalty/rules.py.
    """
    return LoyaltyConfigResponse(
        pointsRuleMode=settings.loyalty_points_rule_mode,
        pointsPerCurrencyUnit=settings.loyalty_points_per_currency_unit,
        pointsRounding=settings.loyalty_points_rounding,
        redemptionValuePerPoint=settings.loyalty_redemption_value_per_point,
        redemptionMinPoints=settings.loyalty_redemption_min_points,
        redemptionMaxPointsPerTx=settings.loyalty_redemption_max_points_per_tx,
    )


@router.post("/earn", response_model=TransactionResponse)
async def earn(
    body: EarnRequest,
    session: Session = Depends(get_db),
    unas_client: UnasClient = Depends(get_unas_client),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> TransactionResponse:
    try:
        result = await service.earn(
            session,
            unas_client,
            settings,
            qr_payload=body.qrPayload,
            external_receipt_id=body.externalReceiptId,
            purchase_amount_gross=body.purchaseAmountGross,
            idempotency_key=body.idempotencyKey,
            store_id=user.store_id,
            register_id=None,
            cashier_user_id=user.id,
        )
    except (LoyaltyServiceError, RuleViolation, UnasApiError) as exc:
        raise _raise_for(exc) from exc
    return _to_response(result)


@router.post("/redeem", response_model=TransactionResponse)
async def redeem(
    body: RedeemRequest,
    session: Session = Depends(get_db),
    unas_client: UnasClient = Depends(get_unas_client),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> TransactionResponse:
    try:
        result = await service.redeem(
            session,
            unas_client,
            settings,
            qr_payload=body.qrPayload,
            external_receipt_id=body.externalReceiptId,
            points_to_redeem=body.pointsToRedeem,
            idempotency_key=body.idempotencyKey,
            store_id=user.store_id,
            register_id=None,
            cashier_user_id=user.id,
        )
    except (LoyaltyServiceError, RuleViolation, UnasApiError) as exc:
        raise _raise_for(exc) from exc
    return _to_response(result)


@router.post("/transactions/{transaction_id}/reverse", response_model=TransactionResponse)
async def reverse_transaction(
    transaction_id: str,
    body: ReverseRequest,
    session: Session = Depends(get_db),
    unas_client: UnasClient = Depends(get_unas_client),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_role("admin")),
) -> TransactionResponse:
    try:
        result = await service.reverse(
            session,
            unas_client,
            settings,
            transaction_id=transaction_id,
            reason=body.reason,
            actor_user_id=user.id,
        )
    except (LoyaltyServiceError, RuleViolation, UnasApiError) as exc:
        raise _raise_for(exc) from exc
    return _to_response(result)


@router.get("/transactions", response_model=list[TransactionListItem])
def list_transactions(
    limit: int = Query(default=25, ge=1, le=200),
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TransactionListItem]:
    stmt = select(LoyaltyTransaction).order_by(LoyaltyTransaction.created_at.desc()).limit(limit)
    if user.role != "admin" and user.store_id:
        stmt = stmt.where(LoyaltyTransaction.store_id == user.store_id)
    rows = session.execute(stmt).scalars().all()
    return [
        TransactionListItem(
            id=row.id,
            type=row.type,
            status=row.status,
            pointsDelta=str(row.points_delta),
            balanceAfter=str(row.balance_after) if row.balance_after is not None else None,
            externalReceiptId=row.external_receipt_id,
            createdAt=row.created_at.isoformat(),
        )
        for row in rows
    ]
