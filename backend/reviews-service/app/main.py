import logging
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deals_client import deals_client
from app.models import Review
from app.schemas import ReviewCreate, ReviewResponse, SellerReviewsResponse
from app.security import get_user_id

logger = logging.getLogger(__name__)
app = FastAPI(title="LEGO Marketplace Reviews Service", version="0.1.0")


async def get_review_context(deal_id: UUID) -> dict:
    try:
        return await deals_client.get_review_context(str(deal_id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        logger.error("Deals returned %s while validating a review", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось проверить сделку")
    except httpx.RequestError:
        logger.exception("Deals service is unavailable while validating a review")
        raise HTTPException(status_code=503, detail="Сервис сделок временно недоступен")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "reviews"}


@app.post(
    "/deals/{deal_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    deal_id: UUID,
    payload: ReviewCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await get_review_context(deal_id)
    if deal["buyer_id"] != str(user_id):
        raise HTTPException(status_code=403, detail="Оставить отзыв может только покупатель")
    if deal["status"] != "COMPLETED" or deal.get("dispute_status") not in {None, "RESOLVED"}:
        raise HTTPException(status_code=409, detail="Отзыв доступен после завершения сделки и спора")

    existing = await db.scalar(select(Review.id).where(Review.deal_id == deal_id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="По этой сделке уже оставлен отзыв")

    review = Review(
        deal_id=deal_id,
        reviewer_id=user_id,
        seller_id=UUID(deal["seller_id"]),
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="По этой сделке уже оставлен отзыв")
    await db.refresh(review)
    return review


@app.get("/users/{seller_id}/reviews", response_model=SellerReviewsResponse)
async def list_seller_reviews(
    seller_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    summary = await db.execute(
        select(func.count(Review.id), func.avg(Review.rating)).where(Review.seller_id == seller_id)
    )
    total, average = summary.one()
    average_rating = Decimal(str(average)).quantize(Decimal("0.01")) if average is not None else None
    result = await db.execute(
        select(Review)
        .where(Review.seller_id == seller_id)
        .order_by(Review.created_at.desc(), Review.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return SellerReviewsResponse(
        seller_id=seller_id,
        total=total,
        average_rating=average_rating,
        reviews=result.scalars().all(),
    )
