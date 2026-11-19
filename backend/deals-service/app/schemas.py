from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    DealStatus,
    DisputeDecision,
    DisputeReason,
    DisputeStatus,
    EvidenceType,
    OfferStatus,
    TransactionType,
)


class OfferCreate(BaseModel):
    listing_id: UUID
    amount: Decimal = Field(gt=0, decimal_places=2)


class CounterOfferCreate(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)


class DealCreate(BaseModel):
    listing_id: UUID
    transaction_type: TransactionType


class ShipmentEventRequest(BaseModel):
    shipment_id: UUID


class OfferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    buyer_id: UUID
    seller_id: UUID
    sender_id: UUID
    recipient_id: UUID
    previous_offer_id: UUID | None
    amount: Decimal
    status: OfferStatus


class DealSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    description: str
    listed_price: Decimal
    condition: str
    completeness: str | None
    missing_parts: str | None
    has_box: bool
    has_instructions: bool
    known_defects: str | None
    image_references: list[str]


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    buyer_id: UUID
    seller_id: UUID
    source_offer_id: UUID | None
    agreed_price: Decimal
    transaction_type: TransactionType
    status: DealStatus
    buyer_confirmed: bool
    seller_confirmed: bool
    snapshot: DealSnapshotResponse
    inspection_deadline_at: datetime | None
    shipment_id: UUID | None


class DisputeCreate(BaseModel):
    reason: DisputeReason
    description: str = Field(min_length=10, max_length=5000)


class EvidenceCreate(BaseModel):
    evidence_type: Literal[EvidenceType.TEXT, EvidenceType.MESSAGE, EvidenceType.TRACKING]
    content: str = Field(min_length=1, max_length=5000)


class DisputeEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submitted_by: UUID
    evidence_type: EvidenceType
    content: str
    created_at: datetime
    image_url: str | None = None


class DisputeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID
    opened_by: UUID
    reason: DisputeReason
    description: str
    status: DisputeStatus
    response_due_at: datetime | None
    deadline_missed_at: datetime | None
    resolution: DisputeDecision | None
    refund_amount: Decimal | None
    resolved_by: UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime
    evidence: list[DisputeEvidenceResponse]


class DisputeRequestEvidence(BaseModel):
    participant: Literal["buyer", "seller"]
    note: str = Field(min_length=1, max_length=2000)


class DisputeResolve(BaseModel):
    decision: DisputeDecision
    refund_amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    note: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_refund_amount(self):
        if self.decision == DisputeDecision.PARTIAL_REFUND and self.refund_amount is None:
            raise ValueError("Для частичного возврата укажите сумму")
        if self.decision != DisputeDecision.PARTIAL_REFUND and self.refund_amount is not None:
            raise ValueError("Сумма допустима только для частичного возврата")
        return self


class DisputeAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: UUID | None
    action: str
    details: dict
    created_at: datetime
