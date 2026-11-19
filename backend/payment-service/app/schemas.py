from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import PaymentStatus, PayoutStatus, RefundStatus


class ProviderWebhook(BaseModel):
    event_id: str = Field(min_length=1, max_length=120)
    event_type: Literal["payment.authorized", "payment.failed"]
    payment_id: UUID
    provider_reference: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID
    buyer_id: UUID
    seller_id: UUID
    buyer_amount: Decimal
    platform_fee: Decimal
    seller_payout: Decimal
    currency: str
    provider: str
    status: PaymentStatus
    created_at: datetime
    demo_mode: bool = True
    demo_notice: str = "Демо-режим: реальные деньги не списываются и не переводятся"


class RefundCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    reason: str = Field(min_length=1, max_length=300)


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    amount: Decimal
    reason: str
    status: RefundStatus
    provider_reference: str | None
    created_at: datetime


class PayoutCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)


class PayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    amount: Decimal
    status: PayoutStatus
    provider_reference: str | None
    created_at: datetime
    released_at: datetime | None
