from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID
    reviewer_id: UUID
    seller_id: UUID
    rating: int
    comment: str | None
    created_at: datetime


class SellerReviewsResponse(BaseModel):
    seller_id: UUID
    total: int
    average_rating: Decimal | None
    reviews: list[ReviewResponse]
