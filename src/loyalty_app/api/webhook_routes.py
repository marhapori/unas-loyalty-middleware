from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from loyalty_app.api.deps import get_db
from loyalty_app.config import Settings, get_settings
from loyalty_app.loyalty.webhook_adapter import mask_payload_for_logging, parse_customer_registration_payload
from loyalty_app.models import WebhookEvent
from loyalty_app.rate_limit import webhook_limiter
from loyalty_app.security import verify_unas_webhook, webhook_event_key

logger = logging.getLogger("loyalty_app.webhook")

router = APIRouter(prefix="/webhooks/unas", tags=["webhooks"])


@router.post("/customer-registration", status_code=status.HTTP_200_OK)
async def customer_registration_webhook(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    webhook_limiter.check("webhook", request.client.host if request.client else "unknown")

    raw_body = await request.body()
    signature = request.headers.get("x-unas-hmac", "")

    if not verify_unas_webhook(raw_body, signature, settings.unas_webhook_hmac_secret):
        logger.warning("rejected unas webhook with invalid/missing HMAC signature")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Ervenytelen alairas")

    event_key = webhook_event_key(raw_body)
    existing = session.execute(
        select(WebhookEvent).where(WebhookEvent.event_key == event_key)
    ).scalar_one_or_none()
    if existing is not None:
        # Duplicate delivery of an already-seen event: acknowledge without reprocessing.
        return {"status": "duplicate"}

    adapted = parse_customer_registration_payload(raw_body)
    event = WebhookEvent(
        event_key=event_key,
        event_type="customer_registration",
        raw_payload_masked=mask_payload_for_logging(raw_body),
        verify_status="verified",
        process_status="received",
    )
    session.add(event)
    session.commit()

    if adapted.unas_customer_id is None:
        logger.info("webhook %s queued, adapter could not extract customer id yet (needs_review on next pass)", event.id)

    return {"status": "accepted"}
