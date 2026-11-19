from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import DealStatus, OfferStatus, TransactionType


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
