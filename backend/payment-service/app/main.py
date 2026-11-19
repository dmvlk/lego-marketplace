import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deals_client import deals_client
from app.fees import calculate_amounts
from app.models import (
    Payment,
    PaymentStatus,
    Payout,
    PayoutStatus,
    ProviderEvent,
    Refund,
    RefundStatus,
)
from app.provider import AuthorizationEvent, provider
from app.schemas import (
    PaymentResponse,
    PayoutCreate,
    PayoutResponse,
    ProviderWebhook,
    RefundCreate,
    RefundResponse,
)
from app.security import get_user_id, require_service_token

logger = logging.getLogger(__name__)
app = FastAPI(title="LEGO Marketplace Payment Service", version="0.5.0")


async def load_payment(db: AsyncSession, payment_id: UUID, for_update: bool = False) -> Payment | None:
    statement = select(Payment).where(Payment.id == payment_id)
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()


def event_payload(event: AuthorizationEvent) -> ProviderWebhook:
    return ProviderWebhook(
        event_id=event.event_id,
        event_type=event.event_type,
        payment_id=event.payment_id,
        provider_reference=event.provider_reference,
        amount=event.amount,
        currency=event.currency,
    )


async def process_provider_event(
    db: AsyncSession,
    payload: ProviderWebhook,
    event_data: dict,
) -> bool:
    payment = await load_payment(db, payload.payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    if (
        payment.provider != provider.name
        or payment.provider_reference != payload.provider_reference
        or payment.buyer_amount != payload.amount
        or payment.currency != payload.currency
    ):
        raise HTTPException(status_code=409, detail="Событие не соответствует платежу")

    event_result = await db.execute(
        select(ProviderEvent)
        .where(
            ProviderEvent.provider == provider.name,
            ProviderEvent.event_id == payload.event_id,
        )
        .with_for_update()
    )
    saved_event = event_result.scalar_one_or_none()
    if saved_event:
        if (
            saved_event.payment_id != payment.id
            or saved_event.event_type != payload.event_type
        ):
            raise HTTPException(status_code=409, detail="Идентификатор события уже использован")
        if saved_event.processed_at:
            return False
    if saved_event is None:
        saved_event = ProviderEvent(
            payment_id=payment.id,
            provider=provider.name,
            event_id=payload.event_id,
            event_type=payload.event_type,
            payload=event_data,
        )
        db.add(saved_event)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            event_result = await db.execute(
                select(ProviderEvent).where(
                    ProviderEvent.provider == provider.name,
                    ProviderEvent.event_id == payload.event_id,
                )
            )
            saved_event = event_result.scalar_one_or_none()
            if saved_event is None:
                raise HTTPException(status_code=409, detail="Событие уже обрабатывается")
            if saved_event.payment_id != payload.payment_id or saved_event.event_type != payload.event_type:
                raise HTTPException(status_code=409, detail="Идентификатор события уже использован")
            if saved_event.processed_at:
                return False

    payment = await load_payment(db, payload.payment_id, for_update=True)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платеж не найден")

    if payload.event_type == "payment.authorized":
        if payment.status == PaymentStatus.FAILED:
            raise HTTPException(status_code=409, detail="Неуспешный платеж нельзя авторизовать")
        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.AUTHORIZED
        await db.commit()

        prior_success_result = await db.execute(
            select(ProviderEvent.id).where(
                ProviderEvent.payment_id == payment.id,
                ProviderEvent.event_type == "payment.authorized",
                ProviderEvent.processed_at.is_not(None),
                ProviderEvent.id != saved_event.id,
            )
        )
        if prior_success_result.first() is None:
            try:
                await deals_client.mark_payment_authorized(str(payment.deal_id))
            except httpx.HTTPStatusError as error:
                if error.response.status_code in {404, 409}:
                    await refund_unpayable_payment(db, payment)
                else:
                    logger.error("Deals returned %s while authorizing payment", error.response.status_code)
                    raise HTTPException(status_code=503, detail="Не удалось обновить состояние сделки")
            except httpx.RequestError:
                logger.exception("Deals service is unavailable while authorizing payment")
                raise HTTPException(status_code=503, detail="Сервис сделок временно недоступен")
    elif payload.event_type == "payment.failed":
        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
            await db.commit()

    saved_event.processed_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def refund_unpayable_payment(db: AsyncSession, payment: Payment) -> None:
    idempotency_key = f"deal-unpayable-{payment.id}"
    result = await db.execute(
        select(Refund).where(
            Refund.payment_id == payment.id,
            Refund.idempotency_key == idempotency_key,
        )
    )
    refund = result.scalar_one_or_none()
    if refund is None:
        refund = Refund(
            payment_id=payment.id,
            amount=payment.buyer_amount,
            reason="Сделка больше не ожидает оплату",
            idempotency_key=idempotency_key,
            status=RefundStatus.PENDING,
        )
        db.add(refund)
        await db.commit()
    if refund.status == RefundStatus.SUCCEEDED:
        return

    refund.provider_reference = await provider.refund(payment.id, idempotency_key)
    refund.status = RefundStatus.SUCCEEDED
    payment.status = PaymentStatus.REFUNDED
    await db.commit()


async def authorize_pending_payment(db: AsyncSession, payment: Payment) -> Payment:
    if payment.status == PaymentStatus.PENDING:
        event = await provider.authorize(
            payment.id,
            payment.buyer_amount,
            payment.currency,
        )
        payment.provider_reference = event.provider_reference
        await db.commit()
        payload = event_payload(event)
        await process_provider_event(db, payload, payload.model_dump(mode="json"))
    elif payment.status == PaymentStatus.AUTHORIZED:
        result = await db.execute(
            select(ProviderEvent).where(
                ProviderEvent.payment_id == payment.id,
                ProviderEvent.event_type == "payment.authorized",
                ProviderEvent.processed_at.is_(None),
            )
        )
        pending_event = result.scalar_one_or_none()
        if pending_event is not None:
            payload = ProviderWebhook.model_validate(pending_event.payload)
            await process_provider_event(db, payload, pending_event.payload)

    refreshed = await load_payment(db, payment.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    return refreshed


async def get_existing_payment(
    db: AsyncSession,
    buyer_id: UUID,
    idempotency_key: str,
) -> Payment | None:
    result = await db.execute(
        select(Payment).where(
            Payment.buyer_id == buyer_id,
            Payment.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def get_total_refunds(db: AsyncSession, payment_id: UUID) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(Refund.amount), Decimal("0.00"))).where(
            Refund.payment_id == payment_id,
            Refund.status.in_([RefundStatus.PENDING, RefundStatus.SUCCEEDED]),
        )
    )
    return result.scalar_one()


async def finish_payout(db: AsyncSession, payout: Payout, payment: Payment) -> Payout:
    if payout.status == PayoutStatus.RELEASED:
        return payout
    payout.provider_reference = await provider.payout(payment.id, payout.idempotency_key)
    payout.status = PayoutStatus.RELEASED
    payout.released_at = datetime.now(timezone.utc)
    payment.status = PaymentStatus.PAID_OUT
    await db.commit()
    return payout


async def finish_refund(db: AsyncSession, refund: Refund, payment: Payment) -> Refund:
    if refund.status == RefundStatus.SUCCEEDED:
        return refund
    refund.provider_reference = await provider.refund(payment.id, refund.idempotency_key)
    refund.status = RefundStatus.SUCCEEDED
    total_refunded = await get_total_refunds(db, payment.id)
    payment.status = (
        PaymentStatus.REFUNDED
        if total_refunded >= payment.buyer_amount
        else PaymentStatus.PARTIALLY_REFUNDED
    )
    await db.commit()
    return refund


async def require_deal_status(deal_id: UUID, allowed_statuses: set[str]) -> None:
    try:
        deal = await deals_client.get_payment_context(str(deal_id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        logger.error("Deals returned %s while validating payment operation", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось проверить сделку")
    except httpx.RequestError:
        logger.exception("Deals service is unavailable while validating payment operation")
        raise HTTPException(status_code=503, detail="Сервис сделок временно недоступен")
    if deal["status"] not in allowed_statuses:
        raise HTTPException(status_code=409, detail="Операция недоступна для текущего состояния сделки")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "payment", "provider": provider.name, "demo_mode": True}


@app.post(
    "/payments/deals/{deal_id}",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_payment(
    deal_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    existing = await get_existing_payment(db, user_id, idempotency_key)
    if existing is not None:
        if existing.deal_id != deal_id:
            raise HTTPException(status_code=409, detail="Ключ идемпотентности уже использован")
        payment = await authorize_pending_payment(db, existing)
        return PaymentResponse.model_validate(payment)

    try:
        deal = await deals_client.get_payment_context(str(deal_id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        logger.error("Deals returned %s while starting payment", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось проверить сделку")
    except httpx.RequestError:
        logger.exception("Deals service is unavailable while starting payment")
        raise HTTPException(status_code=503, detail="Сервис сделок временно недоступен")

    if UUID(deal["buyer_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Оплатить сделку может только покупатель")
    if deal["transaction_type"] != "ONLINE_PROTECTED":
        raise HTTPException(status_code=409, detail="Для офлайн-сделки платеж не требуется")
    if deal["status"] != "AWAITING_PAYMENT":
        raise HTTPException(status_code=409, detail="Сделка больше не ожидает оплату")

    active_result = await db.execute(
        select(Payment).where(
            Payment.deal_id == deal_id,
            Payment.status.in_(
                [
                    PaymentStatus.PENDING,
                    PaymentStatus.AUTHORIZED,
                    PaymentStatus.PARTIALLY_REFUNDED,
                    PaymentStatus.PAID_OUT,
                ]
            ),
        )
    )
    active_payment = active_result.scalar_one_or_none()
    if active_payment is not None:
        raise HTTPException(status_code=409, detail="Для сделки уже есть активный платеж")

    try:
        amounts = calculate_amounts(
            Decimal(deal["amount"]),
            settings.platform_fee_percent,
        )
    except ValueError as error:
        logger.error("Invalid deal amount for payment: %s", error)
        raise HTTPException(status_code=409, detail="Сумма сделки не подходит для оплаты")

    payment = Payment(
        deal_id=deal_id,
        buyer_id=user_id,
        seller_id=UUID(deal["seller_id"]),
        buyer_amount=amounts.buyer_amount,
        platform_fee=amounts.platform_fee,
        seller_payout=amounts.seller_payout,
        currency=settings.payment_currency.upper(),
        provider=provider.name,
        idempotency_key=idempotency_key,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await get_existing_payment(db, user_id, idempotency_key)
        if existing is not None and existing.deal_id == deal_id:
            payment = await authorize_pending_payment(db, existing)
            return PaymentResponse.model_validate(payment)
        raise HTTPException(status_code=409, detail="Для сделки уже есть активный платеж")

    payment = await authorize_pending_payment(db, payment)
    return PaymentResponse.model_validate(payment)


@app.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    payment = await load_payment(db, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    if user_id not in {payment.buyer_id, payment.seller_id}:
        raise HTTPException(status_code=403, detail="Нет доступа к этому платежу")
    return PaymentResponse.model_validate(payment)


@app.post("/payments/webhooks/{provider_name}")
async def payment_webhook(
    provider_name: str,
    request: Request,
    x_provider_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if provider_name != provider.name:
        raise HTTPException(status_code=404, detail="Провайдер не найден")
    body = await request.body()
    if not provider.verify_webhook(body, x_provider_signature):
        raise HTTPException(status_code=401, detail="Недействительная подпись вебхука")
    try:
        payload = ProviderWebhook.model_validate_json(body)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Некорректное событие платежного провайдера")
    processed = await process_provider_event(
        db,
        payload,
        payload.model_dump(mode="json"),
    )
    return {"status": "processed" if processed else "duplicate"}


@app.post(
    "/internal/payments/deals/{deal_id}/refund",
    response_model=RefundResponse,
)
async def refund_deal_payment(
    deal_id: UUID,
    payload: RefundCreate,
    x_service_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_service_token(x_service_token)
    payment_result = await db.execute(
        select(Payment)
        .where(Payment.deal_id == deal_id)
        .order_by(Payment.created_at.desc())
        .with_for_update()
    )
    payment = payment_result.scalars().first()
    if payment is None:
        raise HTTPException(status_code=404, detail="Платеж по сделке не найден")
    existing_result = await db.execute(
        select(Refund).where(
            Refund.payment_id == payment.id,
            Refund.idempotency_key == payload.idempotency_key,
        )
    )
    existing_refund = existing_result.scalar_one_or_none()
    if existing_refund is not None:
        return await finish_refund(db, existing_refund, payment)
    await require_deal_status(deal_id, {"DISPUTED", "CANCELLED"})
    if payment.status not in {
        PaymentStatus.AUTHORIZED,
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.PAID_OUT,
    }:
        raise HTTPException(status_code=409, detail="Платеж нельзя вернуть в текущем состоянии")

    pending_payout = await db.execute(
        select(Payout.id).where(
            Payout.payment_id == payment.id,
            Payout.status == PayoutStatus.PENDING,
        )
    )
    if pending_payout.first() is not None:
        raise HTTPException(status_code=409, detail="Выплата уже выполняется")

    reserved_refunds = await get_total_refunds(db, payment.id)
    remaining = payment.buyer_amount - reserved_refunds
    refund_amount = payload.amount or remaining
    if refund_amount > remaining:
        raise HTTPException(status_code=409, detail="Сумма возврата превышает остаток платежа")
    if refund_amount <= 0:
        raise HTTPException(status_code=409, detail="По платежу больше нечего возвращать")

    refund = Refund(
        payment_id=payment.id,
        amount=refund_amount,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
        status=RefundStatus.PENDING,
    )
    db.add(refund)
    await db.commit()
    refund = await finish_refund(db, refund, payment)
    return RefundResponse.model_validate(refund)


@app.post(
    "/internal/payments/deals/{deal_id}/payout",
    response_model=PayoutResponse,
)
async def release_deal_payout(
    deal_id: UUID,
    payload: PayoutCreate,
    x_service_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    require_service_token(x_service_token)
    existing_result = await db.execute(
        select(Payout)
        .join(Payment, Payment.id == Payout.payment_id)
        .where(Payment.deal_id == deal_id)
    )
    existing_payout = existing_result.scalar_one_or_none()
    if existing_payout is not None:
        existing_payment = await load_payment(db, existing_payout.payment_id, for_update=True)
        if existing_payment is None:
            raise HTTPException(status_code=404, detail="Платеж не найден")
        return await finish_payout(db, existing_payout, existing_payment)

    await require_deal_status(deal_id, {"COMPLETED"})
    payment_result = await db.execute(
        select(Payment)
        .where(Payment.deal_id == deal_id)
        .order_by(Payment.created_at.desc())
        .with_for_update()
    )
    payment = payment_result.scalars().first()
    if payment is None:
        raise HTTPException(status_code=404, detail="Платеж по сделке не найден")
    existing_result = await db.execute(
        select(Payout).where(Payout.payment_id == payment.id)
    )
    existing_payout = existing_result.scalar_one_or_none()
    if existing_payout is not None:
        return await finish_payout(db, existing_payout, payment)
    if payment.status not in {
        PaymentStatus.AUTHORIZED,
        PaymentStatus.PARTIALLY_REFUNDED,
    }:
        raise HTTPException(status_code=409, detail="Выплату нельзя выполнить в текущем состоянии")

    pending_refunds = await db.execute(
        select(Refund.id).where(
            Refund.payment_id == payment.id,
            Refund.status == RefundStatus.PENDING,
        )
    )
    if pending_refunds.first() is not None:
        raise HTTPException(status_code=409, detail="Возврат уже выполняется")

    refunded_amount = await get_total_refunds(db, payment.id)
    remaining = payment.buyer_amount - refunded_amount
    payout_amount = calculate_amounts(
        remaining,
        settings.platform_fee_percent,
    ).seller_payout
    if payout_amount <= 0:
        raise HTTPException(status_code=409, detail="После возвратов сумма выплаты равна нулю")

    payout = Payout(
        payment_id=payment.id,
        amount=payout_amount,
        idempotency_key=payload.idempotency_key,
        status=PayoutStatus.PENDING,
    )
    db.add(payout)
    await db.commit()
    payout = await finish_payout(db, payout, payment)
    return PayoutResponse.model_validate(payout)
