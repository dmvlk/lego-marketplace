from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ShipmentStatus


class ShipmentCreate(BaseModel):
    carrier: str = Field(min_length=2, max_length=100)

    @field_validator("carrier")
    @classmethod
    def strip_carrier(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Укажи название службы доставки")
        return value


class TrackingUpdate(BaseModel):
    tracking_number: str | None = Field(default=None, min_length=3, max_length=120)
    status: ShipmentStatus | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def require_update(self):
        if self.tracking_number is None and self.status is None and self.note is None:
            raise ValueError("Нужно передать трек-номер, статус или примечание")
        return self

    @field_validator("tracking_number")
    @classmethod
    def strip_tracking_number(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if len(value) < 3:
                raise ValueError("Трек-номер слишком короткий")
        return value


class TrackingEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ShipmentStatus
    tracking_number: str | None
    note: str | None
    created_at: datetime


class ShipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID
    buyer_id: UUID
    seller_id: UUID
    carrier: str
    tracking_number: str | None
    status: ShipmentStatus
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tracking_events: list[TrackingEventResponse]
