import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TransactionType(str, enum.Enum):
    OFFLINE = "OFFLINE"
    ONLINE_PROTECTED = "ONLINE_PROTECTED"


class DealStatus(str, enum.Enum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    INSPECTION = "INSPECTION"
    DISPUTED = "DISPUTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class OfferStatus(str, enum.Enum):
    OPEN = "OPEN"
    COUNTERED = "COUNTERED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    source_offer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    agreed_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    status: Mapped[DealStatus] = mapped_column(Enum(DealStatus), nullable=False)
    buyer_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seller_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    snapshot: Mapped["DealListingSnapshot"] = relationship(
        back_populates="deal",
        cascade="all, delete-orphan",
        uselist=False,
    )
    status_history: Mapped[list["DealStatusHistory"]] = relationship(
        back_populates="deal",
        cascade="all, delete-orphan",
        order_by="DealStatusHistory.created_at",
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    recipient_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    previous_offer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("offers.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus), default=OfferStatus.OPEN, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DealListingSnapshot(Base):
    __tablename__ = "deal_listing_snapshots"

    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    listed_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    condition: Mapped[str] = mapped_column(String(30), nullable=False)
    completeness: Mapped[str | None] = mapped_column(String(300))
    missing_parts: Mapped[str | None] = mapped_column(Text)
    has_box: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_instructions: Mapped[bool] = mapped_column(Boolean, nullable=False)
    known_defects: Mapped[str | None] = mapped_column(Text)
    image_references: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    deal: Mapped[Deal] = relationship(back_populates="snapshot")


class DealStatusHistory(Base):
    __tablename__ = "deal_status_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(40))
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deal: Mapped[Deal] = relationship(back_populates="status_history")
