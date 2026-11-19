from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ListingCreate(BaseModel):
    category_id: UUID
    theme_id: UUID | None = None
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    price: Decimal = Field(gt=0, decimal_places=2)
    condition: str
    completeness: str | None = Field(default=None, max_length=300)
    missing_parts: str | None = None
    has_box: bool = False
    has_instructions: bool = False
    known_defects: str | None = None
class ListingUpdate(BaseModel):
    category_id: UUID | None = None
    theme_id: UUID | None = None
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=10, max_length=5000)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    condition: str | None = None
    completeness: str | None = None
    missing_parts: str | None = None
    has_box: bool | None = None
    has_instructions: bool | None = None
    known_defects: str | None = None


class ListingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    category_id: UUID
    theme_id: UUID | None
    title: str
    description: str
    price: Decimal
    condition: str
    completeness: str | None
    missing_parts: str | None
    has_box: bool
    has_instructions: bool
    known_defects: str | None
    status: str
    image_references: list[str]
