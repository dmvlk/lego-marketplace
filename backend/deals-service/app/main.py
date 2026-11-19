import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog_client import catalog_client
from app.database import get_db
from app.models import (
    Deal,
    DealListingSnapshot,
    DealStatus,
    DealStatusHistory,
    Offer,
    OfferStatus,
    TransactionType,
)
from app.schemas import (
    CounterOfferCreate,
    DealCreate,
    DealResponse,
    OfferCreate,
    OfferResponse,
)
from app.rules import can_cancel, initial_status, offline_complete
from app.security import get_user_id

logger = logging.getLogger(__name__)
app = FastAPI(title="LEGO Marketplace Deals Service", version="0.4.0")


async def fetch_listing(listing_id: UUID) -> dict:
    try:
        return await catalog_client.get_listing(str(listing_id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        logger.error("Catalog returned %s while fetching listing", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось проверить объявление")
    except httpx.RequestError:
        logger.exception("Catalog service is unavailable")
        raise HTTPException(status_code=503, detail="Сервис каталога временно недоступен")


async def catalog_action(action: str, listing_id: UUID, deal_id: UUID) -> None:
    try:
        if action == "reserve":
            await catalog_client.reserve(str(listing_id), str(deal_id))
        elif action == "release":
            await catalog_client.release(str(listing_id), str(deal_id))
        else:
            await catalog_client.mark_sold(str(listing_id), str(deal_id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 409:
            raise HTTPException(status_code=409, detail="Объявление уже занято другой сделкой")
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        logger.error("Catalog returned %s during %s", error.response.status_code, action)
        raise HTTPException(status_code=502, detail="Не удалось обновить статус объявления")
    except httpx.RequestError:
        logger.exception("Catalog service is unavailable during %s", action)
        raise HTTPException(status_code=503, detail="Сервис каталога временно недоступен")


async def release_after_failure(listing_id: UUID, deal_id: UUID) -> None:
    try:
        await catalog_client.release(str(listing_id), str(deal_id))
    except httpx.HTTPError:
        logger.exception("Failed to release listing after deal persistence failure")
        raise HTTPException(
            status_code=503,
            detail="Не удалось завершить сделку и снять резерв объявления",
        )


def append_history(
    deal: Deal,
    actor_id: UUID,
    previous_status: DealStatus | None,
    reason: str,
) -> None:
    deal.status_history.append(
        DealStatusHistory(
            actor_id=actor_id,
            previous_status=previous_status.value if previous_status else None,
            new_status=deal.status.value,
            reason=reason,
        )
    )


async def create_deal_record(
    db: AsyncSession,
    listing: dict,
    buyer_id: UUID,
    agreed_price: Decimal,
    transaction_type: TransactionType,
    actor_id: UUID,
    source_offer_id: UUID | None = None,
) -> Deal:
    deal_id = uuid.uuid4()
    deal_initial_status = initial_status(transaction_type)
    deal = Deal(
        id=deal_id,
        listing_id=UUID(str(listing["id"])),
        buyer_id=buyer_id,
        seller_id=UUID(str(listing["seller_id"])),
        source_offer_id=source_offer_id,
        agreed_price=agreed_price,
        transaction_type=transaction_type,
        status=deal_initial_status,
        buyer_confirmed=False,
        seller_confirmed=False,
        snapshot=DealListingSnapshot(
            title=listing["title"],
            description=listing["description"],
            listed_price=listing["price"],
            condition=listing["condition"],
            completeness=listing.get("completeness"),
            missing_parts=listing.get("missing_parts"),
            has_box=listing["has_box"],
            has_instructions=listing["has_instructions"],
            known_defects=listing.get("known_defects"),
            image_references=listing.get("image_references", []),
        ),
    )
    append_history(deal, actor_id, None, "Сделка создана")

    try:
        await catalog_action("reserve", deal.listing_id, deal.id)
    except HTTPException as error:
        if error.status_code in {502, 503}:
            await release_after_failure(deal.listing_id, deal.id)
        raise
    db.add(deal)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        await release_after_failure(deal.listing_id, deal.id)
        raise
    return deal


async def load_deal(db: AsyncSession, deal_id: UUID, for_update: bool = False) -> Deal | None:
    statement = (
        select(Deal)
        .options(selectinload(Deal.snapshot), selectinload(Deal.status_history))
        .where(Deal.id == deal_id)
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "deals"}


@app.post("/offers", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
async def create_offer(
    payload: OfferCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    listing = await fetch_listing(payload.listing_id)
    if listing["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Объявление недоступно для предложений")
    seller_id = UUID(str(listing["seller_id"]))
    if seller_id == user_id:
        raise HTTPException(status_code=403, detail="Нельзя сделать предложение самому себе")
    offer = Offer(
        listing_id=payload.listing_id,
        buyer_id=user_id,
        seller_id=seller_id,
        sender_id=user_id,
        recipient_id=seller_id,
        amount=payload.amount,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return offer


@app.get("/offers", response_model=list[OfferResponse])
async def list_offers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Offer)
        .where((Offer.sender_id == user_id) | (Offer.recipient_id == user_id))
        .order_by(Offer.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()


@app.post("/offers/{offer_id}/counter", response_model=OfferResponse, status_code=201)
async def counter_offer(
    offer_id: UUID,
    payload: CounterOfferCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    offer = await db.get(Offer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    if offer.status != OfferStatus.OPEN:
        raise HTTPException(status_code=409, detail="Предложение больше нельзя изменить")
    if offer.recipient_id != user_id:
        raise HTTPException(status_code=403, detail="Встречное предложение может отправить только получатель")

    counter = Offer(
        listing_id=offer.listing_id,
        buyer_id=offer.buyer_id,
        seller_id=offer.seller_id,
        sender_id=user_id,
        recipient_id=offer.sender_id,
        previous_offer_id=offer.id,
        amount=payload.amount,
    )
    offer.status = OfferStatus.COUNTERED
    db.add(counter)
    await db.commit()
    await db.refresh(counter)
    return counter


@app.post("/offers/{offer_id}/reject", status_code=204)
async def reject_offer(
    offer_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    offer = await db.get(Offer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    if offer.recipient_id != user_id:
        raise HTTPException(status_code=403, detail="Отклонить предложение может только получатель")
    if offer.status != OfferStatus.OPEN:
        raise HTTPException(status_code=409, detail="Предложение больше нельзя изменить")
    offer.status = OfferStatus.REJECTED
    await db.commit()


@app.post("/offers/{offer_id}/accept", response_model=DealResponse, status_code=201)
async def accept_offer(
    offer_id: UUID,
    transaction_type: TransactionType,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    offer = await db.get(Offer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    if offer.recipient_id != user_id:
        raise HTTPException(status_code=403, detail="Принять предложение может только получатель")
    if offer.status != OfferStatus.OPEN:
        raise HTTPException(status_code=409, detail="Предложение больше нельзя принять")
    listing = await fetch_listing(offer.listing_id)
    if listing["seller_id"] != str(offer.seller_id) or listing["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Объявление больше недоступно")

    offer.status = OfferStatus.ACCEPTED
    deal = await create_deal_record(
        db,
        listing,
        offer.buyer_id,
        offer.amount,
        transaction_type,
        user_id,
        source_offer_id=offer.id,
    )
    loaded = await load_deal(db, deal.id)
    return loaded


@app.post("/deals", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: DealCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    listing = await fetch_listing(payload.listing_id)
    if listing["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Объявление недоступно для покупки")
    if UUID(str(listing["seller_id"])) == user_id:
        raise HTTPException(status_code=403, detail="Нельзя купить собственное объявление")
    deal = await create_deal_record(
        db,
        listing,
        user_id,
        Decimal(str(listing["price"])),
        payload.transaction_type,
        user_id,
    )
    return await load_deal(db, deal.id)


@app.get("/deals/purchases", response_model=list[DealResponse])
async def list_purchases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.snapshot))
        .where(Deal.buyer_id == user_id)
        .order_by(Deal.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()


@app.get("/deals/sales", response_model=list[DealResponse])
async def list_sales(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.snapshot))
        .where(Deal.seller_id == user_id)
        .order_by(Deal.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()


@app.get("/deals/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await load_deal(db, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if user_id not in {deal.buyer_id, deal.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этой сделке")
    return deal


@app.post("/deals/{deal_id}/confirm-offline", response_model=DealResponse)
async def confirm_offline_deal(
    deal_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await load_deal(db, deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if user_id not in {deal.buyer_id, deal.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этой сделке")
    if deal.transaction_type != TransactionType.OFFLINE:
        raise HTTPException(status_code=409, detail="Это не офлайн-сделка")
    if deal.status == DealStatus.COMPLETED:
        await catalog_action("sold", deal.listing_id, deal.id)
        return deal
    if deal.status != DealStatus.PENDING_CONFIRMATION:
        raise HTTPException(status_code=409, detail="Сделку нельзя подтвердить в текущем статусе")

    previous_status = deal.status
    if user_id == deal.buyer_id:
        if deal.buyer_confirmed:
            return deal
        deal.buyer_confirmed = True
        reason = "Покупатель подтвердил офлайн-сделку"
    else:
        if deal.seller_confirmed:
            return deal
        deal.seller_confirmed = True
        reason = "Продавец подтвердил офлайн-сделку"

    if offline_complete(deal.buyer_confirmed, deal.seller_confirmed):
        deal.status = DealStatus.COMPLETED
        deal.completed_at = datetime.now(timezone.utc)
        append_history(deal, user_id, previous_status, "Сделка завершена после подтверждения обеих сторон")
    else:
        append_history(deal, user_id, previous_status, reason)
    await db.commit()
    if deal.status == DealStatus.COMPLETED:
        await catalog_action("sold", deal.listing_id, deal.id)
    return await load_deal(db, deal.id)


@app.post("/deals/{deal_id}/cancel", response_model=DealResponse)
async def cancel_deal(
    deal_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await load_deal(db, deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if user_id not in {deal.buyer_id, deal.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этой сделке")
    if deal.status == DealStatus.CANCELLED:
        await catalog_action("release", deal.listing_id, deal.id)
        return deal
    if not can_cancel(deal.status):
        raise HTTPException(status_code=409, detail="Сделку нельзя отменить в текущем статусе")

    previous_status = deal.status
    deal.status = DealStatus.CANCELLED
    append_history(deal, user_id, previous_status, "Сделка отменена участником")
    await db.commit()
    await catalog_action("release", deal.listing_id, deal.id)
    return await load_deal(db, deal.id)
