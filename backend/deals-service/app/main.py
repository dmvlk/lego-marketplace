import asyncio
import hmac
import io
import logging
import re
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog_client import catalog_client
from app.config import settings
from app.database import SessionFactory, get_db
from app.models import (
    Deal,
    DealListingSnapshot,
    DealPayoutOutbox,
    DealStatus,
    DealStatusHistory,
    Dispute,
    DisputeAuditLog,
    DisputeDecision,
    DisputeEvidence,
    DisputeResolutionOutbox,
    DisputeStatus,
    EvidenceType,
    Offer,
    OfferStatus,
    TransactionType,
)
from app.payment_client import payment_client
from app.schemas import (
    CounterOfferCreate,
    DealCreate,
    DealResponse,
    DisputeAuditResponse,
    DisputeCreate,
    DisputeEvidenceResponse,
    DisputeRequestEvidence,
    DisputeResolve,
    DisputeResponse,
    EvidenceCreate,
    OfferCreate,
    OfferResponse,
    ShipmentEventRequest,
)
from app.rules import add_business_days, can_cancel, initial_status, offline_complete
from app.security import decode_authorization, get_admin_id, get_user_id
from app.storage import delete_image, get_image, upload_image

logger = logging.getLogger(__name__)
IMAGE_KEY_PATTERN = re.compile(r"disputes/[0-9a-f-]{36}/[0-9a-f]{32}\.(jpg|png|webp)")


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = asyncio.create_task(inspection_worker())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(title="LEGO Marketplace Deals Service", version="0.5.0", lifespan=lifespan)


def require_service_token(service_token: str | None) -> None:
    if not service_token or not hmac.compare_digest(service_token, settings.service_token):
        raise HTTPException(status_code=401, detail="Недействительный сервисный токен")


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


async def load_dispute(
    db: AsyncSession,
    dispute_id: UUID,
    for_update: bool = False,
) -> Dispute | None:
    statement = (
        select(Dispute)
        .options(selectinload(Dispute.evidence))
        .where(Dispute.id == dispute_id)
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


def dispute_response(dispute: Dispute) -> DisputeResponse:
    return DisputeResponse(
        id=dispute.id,
        deal_id=dispute.deal_id,
        opened_by=dispute.opened_by,
        reason=dispute.reason,
        description=dispute.description,
        status=dispute.status,
        response_due_at=dispute.response_due_at,
        deadline_missed_at=dispute.deadline_missed_at,
        resolution=dispute.resolution,
        refund_amount=dispute.refund_amount,
        resolved_by=dispute.resolved_by,
        resolved_at=dispute.resolved_at,
        resolution_note=dispute.resolution_note,
        created_at=dispute.created_at,
        evidence=[
            DisputeEvidenceResponse(
                id=item.id,
                submitted_by=item.submitted_by,
                evidence_type=item.evidence_type,
                content=item.content,
                created_at=item.created_at,
                image_url=(
                    f"/api/v1/disputes/{dispute.id}/evidence/{item.id}/image"
                    if item.image_key
                    else None
                ),
            )
            for item in dispute.evidence
        ],
    )


async def require_dispute_participant(
    db: AsyncSession,
    dispute: Dispute,
    user_id: UUID,
) -> Deal:
    deal = await db.get(Deal, dispute.deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if user_id not in {deal.buyer_id, deal.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этому спору")
    return deal


def register_dispute_evidence(
    db: AsyncSession,
    dispute: Dispute,
    deal: Deal,
    user_id: UUID,
    evidence: DisputeEvidence,
) -> None:
    if dispute.status in {DisputeStatus.RESOLVING, DisputeStatus.RESOLVED}:
        raise HTTPException(status_code=409, detail="К спору больше нельзя добавить доказательства")
    dispute.evidence.append(evidence)
    if (
        dispute.status == DisputeStatus.WAITING_SELLER
        and user_id == deal.seller_id
    ) or (
        dispute.status == DisputeStatus.WAITING_BUYER
        and user_id == deal.buyer_id
    ):
        dispute.status = DisputeStatus.UNDER_REVIEW
        dispute.response_due_at = None
        dispute.deadline_missed_at = None
    add_dispute_audit(
        db,
        dispute.id,
        user_id,
        "evidence_submitted",
        {"evidence_type": evidence.evidence_type.value},
    )


async def ensure_payout_outbox(db: AsyncSession, deal: Deal) -> None:
    result = await db.execute(
        select(DealPayoutOutbox).where(DealPayoutOutbox.deal_id == deal.id)
    )
    if result.scalar_one_or_none() is None:
        db.add(
            DealPayoutOutbox(
                deal_id=deal.id,
                idempotency_key=f"deal-payout-{deal.id}",
            )
        )


async def complete_due_inspections() -> None:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        result = await db.execute(
            select(Deal)
            .options(selectinload(Deal.status_history))
            .where(
                Deal.status == DealStatus.INSPECTION,
                Deal.inspection_deadline_at <= now,
            )
            .order_by(Deal.inspection_deadline_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        deals = result.scalars().all()
        for deal in deals:
            previous_status = deal.status
            deal.status = DealStatus.COMPLETED
            deal.completed_at = now
            append_history(
                deal,
                deal.buyer_id,
                previous_status,
                "Инспекционный период завершен без спора",
            )
            await ensure_payout_outbox(db, deal)
        if deals:
            await db.commit()


async def process_payout_outbox() -> None:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        result = await db.execute(
            select(DealPayoutOutbox)
            .where(
                DealPayoutOutbox.completed_at.is_(None),
                DealPayoutOutbox.next_attempt_at <= now,
            )
            .order_by(DealPayoutOutbox.next_attempt_at)
            .limit(10)
            .with_for_update(skip_locked=True)
        )
        actions = result.scalars().all()
        for action in actions:
            try:
                await payment_client.release_payout(str(action.deal_id))
            except httpx.HTTPStatusError as error:
                action.attempt_count += 1
                delay = min(60 * 2 ** min(action.attempt_count, 6), 3600)
                action.next_attempt_at = now + timedelta(seconds=delay)
                action.last_error = f"HTTP {error.response.status_code}"
                logger.error(
                    "Payment service returned %s for deal %s payout",
                    error.response.status_code,
                    action.deal_id,
                )
            except httpx.RequestError:
                action.attempt_count += 1
                delay = min(60 * 2 ** min(action.attempt_count, 6), 3600)
                action.next_attempt_at = now + timedelta(seconds=delay)
                action.last_error = "Payment service unavailable"
                logger.exception("Payment service unavailable for deal %s payout", action.deal_id)
            else:
                action.completed_at = now
                action.last_error = None
        if actions:
            await db.commit()


def add_dispute_audit(
    db: AsyncSession,
    dispute_id: UUID,
    actor_id: UUID | None,
    action: str,
    details: dict,
) -> None:
    db.add(
        DisputeAuditLog(
            dispute_id=dispute_id,
            actor_id=actor_id,
            action=action,
            details=details,
        )
    )


async def complete_due_dispute_deadlines() -> None:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        result = await db.execute(
            select(Dispute)
            .where(
                Dispute.status.in_([DisputeStatus.WAITING_SELLER, DisputeStatus.WAITING_BUYER]),
                Dispute.response_due_at <= now,
            )
            .order_by(Dispute.response_due_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        disputes = result.scalars().all()
        for dispute in disputes:
            previous_status = dispute.status
            dispute.status = DisputeStatus.UNDER_REVIEW
            dispute.deadline_missed_at = now
            dispute.response_due_at = None
            add_dispute_audit(
                db,
                dispute.id,
                None,
                "response_deadline_expired",
                {"waiting_for": previous_status.value},
            )
        if disputes:
            await db.commit()


async def process_dispute_resolution_outbox() -> None:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        result = await db.execute(
            select(DisputeResolutionOutbox)
            .where(
                DisputeResolutionOutbox.completed_at.is_(None),
                DisputeResolutionOutbox.next_attempt_at <= now,
            )
            .order_by(DisputeResolutionOutbox.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        actions = result.scalars().all()
        for action in actions:
            dispute = await db.get(Dispute, action.dispute_id)
            deal = await load_deal(db, dispute.deal_id, for_update=True) if dispute else None
            try:
                if (
                    dispute is None
                    or deal is None
                    or dispute.status != DisputeStatus.RESOLVING
                    or dispute.resolved_by is None
                ):
                    raise RuntimeError("Dispute resolution state is inconsistent")

                if action.decision in {
                    DisputeDecision.REFUND_BUYER,
                    DisputeDecision.PARTIAL_REFUND,
                }:
                    await payment_client.refund(
                        str(deal.id),
                        f"dispute-refund-{dispute.id}",
                        dispute.resolution_note or "Решение по спору",
                        str(action.refund_amount) if action.refund_amount is not None else None,
                    )

                if action.decision == DisputeDecision.REFUND_BUYER:
                    await catalog_action("release", deal.listing_id, deal.id)
                    if deal.status != DealStatus.DISPUTED:
                        raise RuntimeError("Deal left disputed state before refund completion")
                    previous_status = deal.status
                    deal.status = DealStatus.CANCELLED
                    append_history(
                        deal,
                        dispute.resolved_by,
                        previous_status,
                        "Администратор решил спор в пользу покупателя",
                    )
                else:
                    if deal.status == DealStatus.DISPUTED:
                        previous_status = deal.status
                        deal.status = DealStatus.COMPLETED
                        deal.completed_at = now
                        append_history(
                            deal,
                            dispute.resolved_by,
                            previous_status,
                            "Администратор решил спор в пользу продавца"
                            if action.decision == DisputeDecision.PAY_SELLER
                            else "Администратор назначил частичный возврат",
                        )
                        action.next_attempt_at = now + timedelta(seconds=10)
                        action.last_error = None
                        await db.commit()
                        continue
                    if deal.status != DealStatus.COMPLETED:
                        raise RuntimeError("Deal left disputed state before payout")
                    await catalog_action("sold", deal.listing_id, deal.id)
                    await payment_client.release_payout(
                        str(deal.id),
                        f"dispute-payout-{dispute.id}",
                    )

                dispute.status = DisputeStatus.RESOLVED
                dispute.resolved_at = now
                action.completed_at = now
                action.last_error = None
                add_dispute_audit(
                    db,
                    dispute.id,
                    dispute.resolved_by,
                    "resolution_completed",
                    {
                        "decision": action.decision.value,
                        "refund_amount": str(action.refund_amount)
                        if action.refund_amount is not None
                        else None,
                    },
                )
            except (HTTPException, httpx.HTTPStatusError, httpx.RequestError, RuntimeError) as error:
                action.attempt_count += 1
                delay = min(60 * 2 ** min(action.attempt_count, 6), 3600)
                action.next_attempt_at = now + timedelta(seconds=delay)
                if isinstance(error, HTTPException):
                    action.last_error = f"HTTP {error.status_code}: {error.detail}"[:300]
                    logger.error(
                        "Dispute %s resolution failed: HTTP %s",
                        action.dispute_id,
                        error.status_code,
                    )
                elif isinstance(error, httpx.HTTPStatusError):
                    action.last_error = f"HTTP {error.response.status_code}"
                    logger.error(
                        "Payment service returned %s while resolving dispute %s",
                        error.response.status_code,
                        action.dispute_id,
                    )
                elif isinstance(error, httpx.RequestError):
                    action.last_error = "Dependent service unavailable"
                    logger.exception("Service unavailable while resolving dispute %s", action.dispute_id)
                else:
                    action.last_error = str(error)[:300]
                    logger.error("Dispute %s resolution state is inconsistent", action.dispute_id)
        if actions:
            await db.commit()


async def inspection_worker() -> None:
    while True:
        try:
            await complete_due_inspections()
            await complete_due_dispute_deadlines()
            await process_payout_outbox()
            await process_dispute_resolution_outbox()
        except SQLAlchemyError:
            logger.exception("Deals background worker database operation failed")
        await asyncio.sleep(10)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "deals"}


@app.get("/internal/deals/{deal_id}/payment")
async def internal_payment_context(
    deal_id: UUID,
    x_service_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_service_token(x_service_token)
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    dispute_status = await db.scalar(
        select(Dispute.status).where(Dispute.deal_id == deal.id)
    )
    return {
        "id": str(deal.id),
        "buyer_id": str(deal.buyer_id),
        "seller_id": str(deal.seller_id),
        "amount": str(deal.agreed_price),
        "transaction_type": deal.transaction_type.value,
        "status": deal.status.value,
        "dispute_status": dispute_status.value if dispute_status else None,
    }


@app.post("/internal/deals/{deal_id}/payment-authorized")
async def internal_payment_authorized(
    deal_id: UUID,
    x_service_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_service_token(x_service_token)
    deal = await load_deal(db, deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if deal.transaction_type != TransactionType.ONLINE_PROTECTED:
        raise HTTPException(status_code=409, detail="Для этой сделки онлайн-оплата недоступна")
    if deal.status == DealStatus.PAID:
        return {"deal_id": str(deal.id), "status": deal.status.value}
    if deal.status != DealStatus.AWAITING_PAYMENT:
        raise HTTPException(status_code=409, detail="Сделка больше не ожидает оплату")

    previous_status = deal.status
    deal.status = DealStatus.PAID
    append_history(deal, deal.buyer_id, previous_status, "Платеж авторизован")
    await db.commit()
    return {"deal_id": str(deal.id), "status": deal.status.value}


@app.get("/internal/deals/{deal_id}/delivery")
async def internal_delivery_context(
    deal_id: UUID,
    x_service_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_service_token(x_service_token)
    deal = await db.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    return {
        "id": str(deal.id),
        "buyer_id": str(deal.buyer_id),
        "seller_id": str(deal.seller_id),
        "transaction_type": deal.transaction_type.value,
        "status": deal.status.value,
        "shipment_id": str(deal.shipment_id) if deal.shipment_id else None,
        "inspection_deadline_at": deal.inspection_deadline_at,
    }


@app.post("/internal/deals/{deal_id}/shipped")
async def internal_mark_shipped(
    deal_id: UUID,
    payload: ShipmentEventRequest,
    x_service_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_service_token(x_service_token)
    deal = await load_deal(db, deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if deal.transaction_type != TransactionType.ONLINE_PROTECTED:
        raise HTTPException(status_code=409, detail="Доставка доступна только для онлайн-сделки")
    if deal.shipment_id is not None and deal.shipment_id != payload.shipment_id:
        raise HTTPException(status_code=409, detail="К сделке уже привязано другое отправление")
    if deal.status == DealStatus.PAID:
        previous_status = deal.status
        deal.shipment_id = payload.shipment_id
        deal.status = DealStatus.SHIPPED
        append_history(deal, deal.seller_id, previous_status, "Продавец передал товар в доставку")
        await db.commit()
    elif deal.shipment_id == payload.shipment_id and deal.status in {
        DealStatus.SHIPPED,
        DealStatus.INSPECTION,
        DealStatus.DISPUTED,
        DealStatus.COMPLETED,
    }:
        return {"deal_id": str(deal.id), "status": deal.status.value}
    else:
        raise HTTPException(status_code=409, detail="Сделка не готова к отправке")
    return {"deal_id": str(deal.id), "status": deal.status.value}


@app.post("/internal/deals/{deal_id}/delivered")
async def internal_mark_delivered(
    deal_id: UUID,
    payload: ShipmentEventRequest,
    x_service_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_service_token(x_service_token)
    deal = await load_deal(db, deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if deal.shipment_id != payload.shipment_id:
        raise HTTPException(status_code=409, detail="Отправление не связано со сделкой")
    if deal.inspection_deadline_at is not None:
        return {
            "deal_id": str(deal.id),
            "status": deal.status.value,
            "inspection_deadline_at": deal.inspection_deadline_at,
        }
    if deal.status != DealStatus.SHIPPED:
        raise HTTPException(status_code=409, detail="Сделка не ожидает подтверждения доставки")

    previous_status = deal.status
    deal.status = DealStatus.INSPECTION
    deal.inspection_deadline_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.inspection_period_hours
    )
    append_history(deal, deal.seller_id, previous_status, "Доставка подтверждена, начат осмотр")
    await db.commit()
    return {
        "deal_id": str(deal.id),
        "status": deal.status.value,
        "inspection_deadline_at": deal.inspection_deadline_at,
    }


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


@app.post("/deals/{deal_id}/inspection/confirm", response_model=DealResponse)
async def confirm_inspection(
    deal_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await load_deal(db, deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if user_id != deal.buyer_id:
        raise HTTPException(status_code=403, detail="Подтвердить получение может только покупатель")
    if deal.transaction_type != TransactionType.ONLINE_PROTECTED:
        raise HTTPException(status_code=409, detail="Осмотр доступен только для онлайн-сделки")
    if deal.status == DealStatus.INSPECTION:
        previous_status = deal.status
        deal.status = DealStatus.COMPLETED
        deal.completed_at = datetime.now(timezone.utc)
        append_history(deal, user_id, previous_status, "Покупатель подтвердил получение товара")
        await ensure_payout_outbox(db, deal)
        await db.commit()
    elif deal.status == DealStatus.COMPLETED:
        active_dispute = await db.scalar(
            select(Dispute.id).where(
                Dispute.deal_id == deal.id,
                Dispute.status != DisputeStatus.RESOLVED,
            )
        )
        if active_dispute is not None:
            raise HTTPException(status_code=409, detail="Спор по сделке еще не разрешен")
        await ensure_payout_outbox(db, deal)
        await db.commit()
    else:
        raise HTTPException(status_code=409, detail="Сделка не находится на этапе осмотра")

    await process_payout_outbox()
    return await load_deal(db, deal.id)


@app.post(
    "/deals/{deal_id}/disputes",
    response_model=DisputeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def open_dispute(
    deal_id: UUID,
    payload: DisputeCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await load_deal(db, deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if user_id != deal.buyer_id:
        raise HTTPException(status_code=403, detail="Открыть спор может только покупатель")
    if deal.transaction_type != TransactionType.ONLINE_PROTECTED:
        raise HTTPException(status_code=409, detail="Спор доступен только для защищенной сделки")
    if deal.status not in {DealStatus.PAID, DealStatus.SHIPPED, DealStatus.INSPECTION}:
        raise HTTPException(status_code=409, detail="Сделку нельзя оспорить в текущем статусе")
    now = datetime.now(timezone.utc)
    if (
        deal.status == DealStatus.INSPECTION
        and deal.inspection_deadline_at is not None
        and deal.inspection_deadline_at <= now
    ):
        raise HTTPException(status_code=409, detail="Срок осмотра уже завершен")

    previous_status = deal.status
    deal.status = DealStatus.DISPUTED
    append_history(deal, user_id, previous_status, "Покупатель открыл спор")
    dispute = Dispute(
        deal_id=deal.id,
        opened_by=user_id,
        reason=payload.reason,
        description=payload.description,
        status=DisputeStatus.WAITING_SELLER,
        response_due_at=add_business_days(now, 2),
    )
    db.add(dispute)
    try:
        await db.flush()
        add_dispute_audit(
            db,
            dispute.id,
            user_id,
            "dispute_opened",
            {"reason": payload.reason.value},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="По этой сделке уже открыт спор")
    loaded = await load_dispute(db, dispute.id)
    return dispute_response(loaded)


@app.get("/disputes/{dispute_id}", response_model=DisputeResponse)
async def get_dispute(
    dispute_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    dispute = await load_dispute(db, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Спор не найден")
    await require_dispute_participant(db, dispute, user_id)
    return dispute_response(dispute)


@app.post(
    "/disputes/{dispute_id}/evidence",
    response_model=DisputeEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_dispute_evidence(
    dispute_id: UUID,
    payload: EvidenceCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    dispute = await load_dispute(db, dispute_id, for_update=True)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Спор не найден")
    deal = await require_dispute_participant(db, dispute, user_id)
    evidence = DisputeEvidence(
        submitted_by=user_id,
        evidence_type=payload.evidence_type,
        content=payload.content,
    )
    register_dispute_evidence(db, dispute, deal, user_id, evidence)
    await db.commit()
    await db.refresh(evidence)
    return DisputeEvidenceResponse.model_validate(evidence)


@app.post(
    "/disputes/{dispute_id}/evidence/images",
    response_model=DisputeEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dispute_image(
    dispute_id: UUID,
    file: UploadFile = File(...),
    description: str = Form(default="", max_length=5000),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    dispute = await load_dispute(db, dispute_id, for_update=True)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Спор не найден")
    deal = await require_dispute_participant(db, dispute, user_id)
    if dispute.status in {DisputeStatus.RESOLVING, DisputeStatus.RESOLVED}:
        raise HTTPException(status_code=409, detail="К спору больше нельзя добавить доказательства")

    data = await file.read(settings.max_image_size_bytes + 1)
    if len(data) > settings.max_image_size_bytes:
        raise HTTPException(status_code=413, detail="Размер фото не должен превышать 5 МБ")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=415, detail="Файл не является корректным изображением")
    if image_format not in {"JPEG", "PNG", "WEBP"}:
        raise HTTPException(status_code=415, detail="Поддерживаются только JPEG, PNG и WebP")
    if width > 10000 or height > 10000 or width * height > 25_000_000:
        raise HTTPException(status_code=413, detail="Слишком большое разрешение фото")

    extension, content_type = {
        "JPEG": ("jpg", "image/jpeg"),
        "PNG": ("png", "image/png"),
        "WEBP": ("webp", "image/webp"),
    }[image_format]
    key = f"disputes/{dispute.id}/{uuid.uuid4().hex}.{extension}"
    try:
        await asyncio.to_thread(upload_image, key, data, content_type)
    except (BotoCoreError, ClientError):
        logger.exception("Failed to upload dispute evidence image")
        raise HTTPException(status_code=503, detail="Не удалось сохранить фото")

    evidence = DisputeEvidence(
        submitted_by=user_id,
        evidence_type=EvidenceType.IMAGE,
        content=description,
        image_key=key,
    )
    register_dispute_evidence(db, dispute, deal, user_id, evidence)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        try:
            await asyncio.to_thread(delete_image, key)
        except (BotoCoreError, ClientError):
            logger.exception("Failed to remove orphaned dispute evidence image")
        logger.exception("Failed to save dispute image evidence")
        raise HTTPException(status_code=500, detail="Не удалось сохранить доказательство")
    await db.refresh(evidence)
    return DisputeEvidenceResponse(
        id=evidence.id,
        submitted_by=evidence.submitted_by,
        evidence_type=evidence.evidence_type,
        content=evidence.content,
        created_at=evidence.created_at,
        image_url=f"/api/v1/disputes/{dispute.id}/evidence/{evidence.id}/image",
    )


@app.get("/disputes/{dispute_id}/evidence/{evidence_id}/image")
async def get_dispute_evidence_image(
    dispute_id: UUID,
    evidence_id: UUID,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_authorization(authorization)
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Недействительный токен")

    dispute = await load_dispute(db, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Спор не найден")
    deal = await db.get(Deal, dispute.deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if payload.get("role") != "ADMIN" and user_id not in {deal.buyer_id, deal.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этому спору")
    evidence = await db.get(DisputeEvidence, evidence_id)
    if (
        evidence is None
        or evidence.dispute_id != dispute.id
        or evidence.image_key is None
        or IMAGE_KEY_PATTERN.fullmatch(evidence.image_key) is None
    ):
        raise HTTPException(status_code=404, detail="Фото не найдено")
    try:
        image = await asyncio.to_thread(get_image, evidence.image_key)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            raise HTTPException(status_code=404, detail="Фото не найдено")
        logger.exception("Failed to read dispute evidence image")
        raise HTTPException(status_code=503, detail="Не удалось загрузить фото")
    except BotoCoreError:
        logger.exception("Failed to read dispute evidence image")
        raise HTTPException(status_code=503, detail="Не удалось загрузить фото")
    return Response(
        content=image["Body"].read(),
        media_type=image.get("ContentType", "application/octet-stream"),
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/admin/disputes", response_model=list[DisputeResponse])
async def list_disputes(
    dispute_status: DisputeStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin_id: UUID = Depends(get_admin_id),
    db: AsyncSession = Depends(get_db),
):
    statement = select(Dispute).options(selectinload(Dispute.evidence))
    if dispute_status is not None:
        statement = statement.where(Dispute.status == dispute_status)
    result = await db.execute(
        statement.order_by(Dispute.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [dispute_response(item) for item in result.scalars().all()]


@app.get("/admin/disputes/{dispute_id}/audit", response_model=list[DisputeAuditResponse])
async def get_dispute_audit(
    dispute_id: UUID,
    admin_id: UUID = Depends(get_admin_id),
    db: AsyncSession = Depends(get_db),
):
    if await db.get(Dispute, dispute_id) is None:
        raise HTTPException(status_code=404, detail="Спор не найден")
    result = await db.execute(
        select(DisputeAuditLog)
        .where(DisputeAuditLog.dispute_id == dispute_id)
        .order_by(DisputeAuditLog.created_at)
    )
    return result.scalars().all()


@app.post("/admin/disputes/{dispute_id}/request-evidence", response_model=DisputeResponse)
async def request_dispute_evidence(
    dispute_id: UUID,
    payload: DisputeRequestEvidence,
    admin_id: UUID = Depends(get_admin_id),
    db: AsyncSession = Depends(get_db),
):
    dispute = await load_dispute(db, dispute_id, for_update=True)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Спор не найден")
    if dispute.status in {DisputeStatus.RESOLVING, DisputeStatus.RESOLVED}:
        raise HTTPException(status_code=409, detail="Спор уже разрешается или закрыт")
    deal = await db.get(Deal, dispute.deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")

    if payload.participant == "buyer":
        dispute.status = DisputeStatus.WAITING_BUYER
    else:
        dispute.status = DisputeStatus.WAITING_SELLER
    dispute.response_due_at = add_business_days(datetime.now(timezone.utc), 2)
    dispute.deadline_missed_at = None
    add_dispute_audit(
        db,
        dispute.id,
        admin_id,
        "evidence_requested",
        {"participant": payload.participant, "note": payload.note},
    )
    await db.commit()
    return dispute_response(await load_dispute(db, dispute.id))


@app.post(
    "/admin/disputes/{dispute_id}/resolve",
    response_model=DisputeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resolve_dispute(
    dispute_id: UUID,
    payload: DisputeResolve,
    admin_id: UUID = Depends(get_admin_id),
    db: AsyncSession = Depends(get_db),
):
    dispute = await load_dispute(db, dispute_id, for_update=True)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Спор не найден")
    if dispute.status in {DisputeStatus.RESOLVING, DisputeStatus.RESOLVED}:
        raise HTTPException(status_code=409, detail="Спор уже разрешается или закрыт")
    deal = await load_deal(db, dispute.deal_id, for_update=True)
    if deal is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if deal.status != DealStatus.DISPUTED:
        raise HTTPException(status_code=409, detail="Сделка больше не находится в споре")
    if (
        payload.decision == DisputeDecision.PARTIAL_REFUND
        and payload.refund_amount >= deal.agreed_price
    ):
        raise HTTPException(
            status_code=422,
            detail="Частичный возврат должен быть меньше суммы сделки",
        )

    dispute.status = DisputeStatus.RESOLVING
    dispute.resolution = payload.decision
    dispute.refund_amount = payload.refund_amount
    dispute.resolved_by = admin_id
    dispute.resolution_note = payload.note
    db.add(
        DisputeResolutionOutbox(
            dispute_id=dispute.id,
            decision=payload.decision,
            refund_amount=payload.refund_amount,
        )
    )
    add_dispute_audit(
        db,
        dispute.id,
        admin_id,
        "resolution_started",
        {
            "decision": payload.decision.value,
            "refund_amount": str(payload.refund_amount)
            if payload.refund_amount is not None
            else None,
            "note": payload.note,
        },
    )
    await db.commit()
    return dispute_response(await load_dispute(db, dispute.id))


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
