import asyncio
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import SessionFactory, get_db
from app.deals_client import deals_client
from app.models import Shipment, ShipmentStatus, TrackingEvent
from app.rules import can_confirm_delivery, can_update_tracking
from app.schemas import ShipmentCreate, ShipmentResponse, TrackingUpdate
from app.security import get_user_id

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = asyncio.create_task(sync_worker())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(title="LEGO Marketplace Delivery Service", version="0.5.0", lifespan=lifespan)


async def load_shipment(
    db: AsyncSession,
    shipment_id: UUID,
    for_update: bool = False,
) -> Shipment | None:
    statement = (
        select(Shipment)
        .options(selectinload(Shipment.tracking_events))
        .where(Shipment.id == shipment_id)
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def find_shipment_by_deal(db: AsyncSession, deal_id: UUID) -> Shipment | None:
    result = await db.execute(
        select(Shipment)
        .options(selectinload(Shipment.tracking_events))
        .where(Shipment.deal_id == deal_id)
    )
    return result.scalar_one_or_none()


async def fetch_deal_context(deal_id: UUID) -> dict:
    try:
        return await deals_client.get_context(str(deal_id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        logger.error("Deals returned %s while checking delivery", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось проверить сделку")
    except httpx.RequestError:
        logger.exception("Deals service is unavailable while checking delivery")
        raise HTTPException(status_code=503, detail="Сервис сделок временно недоступен")


async def ensure_shipped_sync(db: AsyncSession, shipment: Shipment) -> None:
    if shipment.deal_shipped_synced:
        return
    try:
        await deals_client.mark_shipped(str(shipment.deal_id), str(shipment.id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        if error.response.status_code == 409:
            raise HTTPException(status_code=409, detail="Сделка не готова к отправке")
        logger.error("Deals returned %s while marking shipment", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось обновить состояние сделки")
    except httpx.RequestError:
        logger.exception("Deals service is unavailable while marking shipment")
        raise HTTPException(status_code=503, detail="Сервис сделок временно недоступен")
    shipment.deal_shipped_synced = True
    await db.commit()


async def ensure_delivered_sync(db: AsyncSession, shipment: Shipment) -> None:
    if shipment.deal_delivered_synced:
        return
    await ensure_shipped_sync(db, shipment)
    try:
        await deals_client.mark_delivered(str(shipment.deal_id), str(shipment.id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        if error.response.status_code == 409:
            raise HTTPException(status_code=409, detail="Сделка не ожидает эту доставку")
        logger.error("Deals returned %s while confirming delivery", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось начать инспекционный период")
    except httpx.RequestError:
        logger.exception("Deals service is unavailable while confirming delivery")
        raise HTTPException(status_code=503, detail="Сервис сделок временно недоступен")
    shipment.deal_delivered_synced = True
    await db.commit()


async def sync_pending_deals() -> None:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        result = await db.execute(
            select(Shipment)
            .where(
                Shipment.sync_next_attempt_at <= now,
                or_(
                    Shipment.deal_shipped_synced.is_(False),
                    and_(
                        Shipment.status == ShipmentStatus.DELIVERED,
                        Shipment.deal_delivered_synced.is_(False),
                    ),
                ),
            )
            .order_by(Shipment.sync_next_attempt_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        )
        shipments = result.scalars().all()
        for shipment in shipments:
            try:
                await ensure_shipped_sync(db, shipment)
                if shipment.status == ShipmentStatus.DELIVERED:
                    await ensure_delivered_sync(db, shipment)
            except HTTPException as error:
                shipment.sync_attempt_count += 1
                delay = min(10 * 2 ** min(shipment.sync_attempt_count, 5), 300)
                shipment.sync_next_attempt_at = now + timedelta(seconds=delay)
                shipment.sync_last_error = str(error.detail)[:300]
                logger.warning(
                    "Could not sync shipment %s with Deals: %s",
                    shipment.id,
                    error.detail,
                )
                await db.commit()
            else:
                shipment.sync_attempt_count = 0
                shipment.sync_next_attempt_at = now
                shipment.sync_last_error = None
                await db.commit()


async def sync_worker() -> None:
    while True:
        try:
            await sync_pending_deals()
        except SQLAlchemyError:
            logger.exception("Delivery synchronization worker database operation failed")
        await asyncio.sleep(10)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "delivery"}


@app.post(
    "/deliveries/deals/{deal_id}/ship",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shipment(
    deal_id: UUID,
    payload: ShipmentCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await fetch_deal_context(deal_id)
    if UUID(deal["seller_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Отправление может создать только продавец")
    if deal["transaction_type"] != "ONLINE_PROTECTED":
        raise HTTPException(status_code=409, detail="Доставка доступна только для онлайн-сделки")

    existing = await find_shipment_by_deal(db, deal_id)
    if existing is not None:
        if existing.seller_id != user_id:
            raise HTTPException(status_code=403, detail="Нет доступа к этому отправлению")
        await ensure_shipped_sync(db, existing)
        return ShipmentResponse.model_validate(await load_shipment(db, existing.id))
    if deal["status"] != "PAID":
        raise HTTPException(status_code=409, detail="Сделка не готова к отправке")

    shipment = Shipment(
        id=uuid.uuid4(),
        deal_id=deal_id,
        buyer_id=UUID(deal["buyer_id"]),
        seller_id=user_id,
        carrier=payload.carrier.strip(),
        status=ShipmentStatus.CREATED,
    )
    shipment.tracking_events.append(
        TrackingEvent(
            status=ShipmentStatus.CREATED,
            note="Отправление создано",
        )
    )
    db.add(shipment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await find_shipment_by_deal(db, deal_id)
        if existing is None:
            raise HTTPException(status_code=409, detail="Для сделки уже создано отправление")
        if existing.seller_id != user_id:
            raise HTTPException(status_code=403, detail="Нет доступа к этому отправлению")
        shipment = existing

    await ensure_shipped_sync(db, shipment)
    loaded = await load_shipment(db, shipment.id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Отправление не найдено")
    return ShipmentResponse.model_validate(loaded)


@app.get("/deliveries/deals/{deal_id}", response_model=ShipmentResponse)
async def get_shipment_by_deal(
    deal_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    shipment = await find_shipment_by_deal(db, deal_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Отправление не найдено")
    if user_id not in {shipment.buyer_id, shipment.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этому отправлению")
    return ShipmentResponse.model_validate(shipment)


@app.get("/deliveries/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    shipment = await load_shipment(db, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Отправление не найдено")
    if user_id not in {shipment.buyer_id, shipment.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этому отправлению")
    return ShipmentResponse.model_validate(shipment)


@app.patch("/deliveries/{shipment_id}/tracking", response_model=ShipmentResponse)
async def update_tracking(
    shipment_id: UUID,
    payload: TrackingUpdate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    shipment = await load_shipment(db, shipment_id, for_update=True)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Отправление не найдено")
    if shipment.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Изменить доставку может только продавец")
    if not can_update_tracking(
        shipment.status,
        payload.status,
        payload.tracking_number,
        shipment.tracking_number,
    ):
        raise HTTPException(status_code=409, detail="Недопустимый переход статуса доставки")

    if payload.tracking_number is not None:
        shipment.tracking_number = payload.tracking_number.strip()
    if payload.status is not None:
        shipment.status = payload.status
    shipment.tracking_events.append(
        TrackingEvent(
            status=shipment.status,
            tracking_number=shipment.tracking_number,
            note=payload.note,
        )
    )
    await db.commit()
    loaded = await load_shipment(db, shipment.id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Отправление не найдено")
    return ShipmentResponse.model_validate(loaded)


@app.post("/deliveries/{shipment_id}/delivered", response_model=ShipmentResponse)
async def confirm_delivery(
    shipment_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    shipment = await load_shipment(db, shipment_id, for_update=True)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Отправление не найдено")
    if shipment.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Подтвердить доставку может только продавец")

    if shipment.delivered_at is None:
        if not can_confirm_delivery(shipment.status, shipment.tracking_number):
            raise HTTPException(status_code=409, detail="Отправление не готово к подтверждению доставки")
        shipment.status = ShipmentStatus.DELIVERED
        shipment.delivered_at = datetime.now(timezone.utc)
        shipment.tracking_events.append(
            TrackingEvent(
                status=ShipmentStatus.DELIVERED,
                tracking_number=shipment.tracking_number,
                note="Доставка подтверждена",
            )
        )
        await db.commit()

    await ensure_delivered_sync(db, shipment)
    loaded = await load_shipment(db, shipment.id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Отправление не найдено")
    return ShipmentResponse.model_validate(loaded)
