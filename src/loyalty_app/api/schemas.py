from __future__ import annotations

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    qrPayload: str = Field(min_length=1, max_length=300)


class ScanCustomer(BaseModel):
    displayName: str | None
    maskedCardId: str


class ScanResponse(BaseModel):
    customer: ScanCustomer
    pointsBalance: str
    currencyOrUnit: str = "point"


class EarnRequest(BaseModel):
    qrPayload: str = Field(min_length=1, max_length=300)
    externalReceiptId: str = Field(min_length=1, max_length=200)
    purchaseAmountGross: int = Field(ge=0)
    idempotencyKey: str = Field(min_length=1, max_length=255)


class RedeemRequest(BaseModel):
    qrPayload: str = Field(min_length=1, max_length=300)
    externalReceiptId: str = Field(min_length=1, max_length=200)
    pointsToRedeem: int = Field(gt=0)
    idempotencyKey: str = Field(min_length=1, max_length=255)


class ReverseRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class TransactionResponse(BaseModel):
    transactionId: str
    status: str
    balanceBefore: str
    balanceAfter: str
    pointsDelta: str


class LoyaltyConfigResponse(BaseModel):
    pointsRuleMode: str
    pointsPerCurrencyUnit: float
    pointsRounding: str
    redemptionValuePerPoint: float
    redemptionMinPoints: int
    redemptionMaxPointsPerTx: int


class AdminBootstrapRequest(BaseModel):
    storeName: str = Field(min_length=1, max_length=200)
    storeCode: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(default="admin", pattern="^(admin|cashier)$")


class AdminBootstrapResponse(BaseModel):
    storeCreated: bool
    userCreated: bool


class TransactionListItem(BaseModel):
    id: str
    type: str
    status: str
    pointsDelta: str
    balanceAfter: str | None
    externalReceiptId: str | None
    createdAt: str
