import asyncio
import io
import logging
import re
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import settings
from app.models import (
    Category,
    Favorite,
    Listing,
    ListingCondition,
    ListingImage,
    ListingStatus,
    Theme,
)
from app.schemas import ListingCreate, ListingResponse, ListingUpdate
from app.security import get_user_id
from app.storage import delete_image, ensure_bucket, get_image, upload_image

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(ensure_bucket)
    yield


app = FastAPI(title="LEGO Marketplace Catalog Service", version="0.3.0", lifespan=lifespan)


def listing_response(listing: Listing) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        seller_id=listing.seller_id,
        category_id=listing.category_id,
        theme_id=listing.theme_id,
        title=listing.title,
        description=listing.description,
        price=listing.price,
        condition=listing.condition.value,
        completeness=listing.completeness,
        missing_parts=listing.missing_parts,
        has_box=listing.has_box,
        has_instructions=listing.has_instructions,
        known_defects=listing.known_defects,
        status=listing.status.value,
        image_references=[f"/api/v1/catalog/images/{image.object_reference}" for image in listing.images],
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "catalog"}


@app.get("/catalog/categories")
async def categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return [{"id": item.id, "name": item.name, "slug": item.slug} for item in result.scalars()]


@app.get("/catalog/themes")
async def themes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Theme).order_by(Theme.name))
    return [{"id": item.id, "name": item.name, "slug": item.slug} for item in result.scalars()]


@app.get("/catalog/listings")
async def list_listings(
    q: str | None = None,
    category_id: UUID | None = None,
    theme_id: UUID | None = None,
    condition: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    sort: str = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="Минимальная цена не может быть больше максимальной")
    if sort not in {"newest", "price_asc", "price_desc"}:
        raise HTTPException(status_code=422, detail="Недопустимый способ сортировки")

    stmt = select(Listing).options(selectinload(Listing.images)).where(Listing.status == ListingStatus.ACTIVE)
    if q:
        stmt = stmt.where(Listing.title.ilike(f"%{q}%"))
    if category_id:
        stmt = stmt.where(Listing.category_id == category_id)
    if theme_id:
        stmt = stmt.where(Listing.theme_id == theme_id)
    if condition:
        try:
            stmt = stmt.where(Listing.condition == ListingCondition(condition))
        except ValueError:
            raise HTTPException(status_code=422, detail="Недопустимое состояние товара")
    if min_price is not None:
        stmt = stmt.where(Listing.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Listing.price <= max_price)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()
    if sort == "price_asc":
        stmt = stmt.order_by(Listing.price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Listing.price.desc())
    elif sort == "newest":
        stmt = stmt.order_by(Listing.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = [listing_response(item) for item in result.scalars()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/catalog/favorites")
async def list_favorites(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    base_query = (
        select(Listing)
        .join(Favorite, Favorite.listing_id == Listing.id)
        .where(Favorite.user_id == user_id, Listing.status == ListingStatus.ACTIVE)
    )
    total = (
        await db.execute(select(func.count()).select_from(base_query.subquery()))
    ).scalar_one()
    result = await db.execute(
        base_query.options(selectinload(Listing.images))
        .order_by(Listing.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [listing_response(item) for item in result.scalars()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/catalog/listings/{listing_id}", response_model=ListingResponse)
async def get_listing(listing_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Listing).options(selectinload(Listing.images)).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if listing is None or listing.status in {ListingStatus.BLOCKED, ListingStatus.ARCHIVED}:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    return listing_response(listing)


@app.post("/catalog/listings", response_model=ListingResponse, status_code=201)
async def create_listing(
    payload: ListingCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    if await db.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=422, detail="Категория не найдена")
    if payload.theme_id and await db.get(Theme, payload.theme_id) is None:
        raise HTTPException(status_code=422, detail="Тема не найдена")
    try:
        condition = ListingCondition(payload.condition)
    except ValueError:
        raise HTTPException(status_code=422, detail="Недопустимое состояние товара")

    listing = Listing(
        seller_id=user_id,
        category_id=payload.category_id,
        theme_id=payload.theme_id,
        title=payload.title,
        description=payload.description,
        price=payload.price,
        condition=condition,
        completeness=payload.completeness,
        missing_parts=payload.missing_parts,
        has_box=payload.has_box,
        has_instructions=payload.has_instructions,
        known_defects=payload.known_defects,
        status=ListingStatus.ACTIVE,
        images=[],
    )
    db.add(listing)
    await db.flush()
    await db.commit()
    return listing_response(listing)


@app.post("/catalog/listings/{listing_id}/images", status_code=201)
async def upload_listing_image(
    listing_id: UUID,
    file: UploadFile = File(...),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Listing).options(selectinload(Listing.images)).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    if listing.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Нельзя изменить чужое объявление")
    if listing.status not in {ListingStatus.ACTIVE, ListingStatus.DRAFT}:
        raise HTTPException(status_code=409, detail="К этому объявлению нельзя добавить фото")
    if len(listing.images) >= 10:
        raise HTTPException(status_code=422, detail="К объявлению можно добавить не более 10 фото")

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
    key = f"{listing.id}/{uuid.uuid4().hex}.{extension}"
    try:
        await asyncio.to_thread(upload_image, key, data, content_type)
    except (BotoCoreError, ClientError):
        logger.exception("Failed to upload listing image to object storage")
        raise HTTPException(status_code=503, detail="Не удалось сохранить фото")

    listing.images.append(ListingImage(object_reference=key, sort_order=len(listing.images)))
    await db.flush()
    image_id = listing.images[-1].id
    await db.commit()
    return {
        "image_id": image_id,
        "image_reference": f"/api/v1/catalog/images/{key}",
    }


@app.get("/catalog/images/{key:path}")
async def serve_listing_image(key: str):
    if not re.fullmatch(r"[0-9a-f-]{36}/[0-9a-f]{32}\.(jpg|png|webp)", key):
        raise HTTPException(status_code=404, detail="Фото не найдено")
    try:
        image = await asyncio.to_thread(get_image, key)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            raise HTTPException(status_code=404, detail="Фото не найдено")
        logger.exception("Failed to read listing image from object storage")
        raise HTTPException(status_code=503, detail="Не удалось загрузить фото")
    except BotoCoreError:
        logger.exception("Failed to read listing image from object storage")
        raise HTTPException(status_code=503, detail="Не удалось загрузить фото")
    return Response(
        content=image["Body"].read(),
        media_type=image.get("ContentType", "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.delete("/catalog/listings/{listing_id}/images/{image_id}", status_code=204)
async def remove_listing_image(
    listing_id: UUID,
    image_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    if listing.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Нельзя изменить чужое объявление")
    if listing.status not in {ListingStatus.ACTIVE, ListingStatus.DRAFT}:
        raise HTTPException(status_code=409, detail="Это фото нельзя удалить в текущем статусе")
    image = await db.get(ListingImage, image_id)
    if image is None or image.listing_id != listing.id:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    try:
        await asyncio.to_thread(delete_image, image.object_reference)
    except (BotoCoreError, ClientError):
        logger.exception("Failed to delete listing image from object storage")
        raise HTTPException(status_code=503, detail="Не удалось удалить фото")
    await db.delete(image)
    await db.commit()


@app.patch("/catalog/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: UUID,
    payload: ListingUpdate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Listing).options(selectinload(Listing.images)).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    if listing.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Нельзя изменить чужое объявление")
    if listing.status not in {ListingStatus.ACTIVE, ListingStatus.DRAFT}:
        raise HTTPException(status_code=409, detail="Это объявление нельзя изменить в текущем статусе")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "condition" and value is not None:
            try:
                value = ListingCondition(value)
            except ValueError:
                raise HTTPException(status_code=422, detail="Недопустимое состояние товара")
        elif field == "category_id" and value is not None:
            if await db.get(Category, value) is None:
                raise HTTPException(status_code=422, detail="Категория не найдена")
        elif field == "theme_id" and value is not None:
            if await db.get(Theme, value) is None:
                raise HTTPException(status_code=422, detail="Тема не найдена")
        setattr(listing, field, value)
    await db.commit()
    return listing_response(listing)


@app.delete("/catalog/listings/{listing_id}", status_code=204)
async def archive_listing(
    listing_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    if listing.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Нельзя удалить чужое объявление")
    listing.status = ListingStatus.ARCHIVED
    await db.commit()


@app.post("/catalog/listings/{listing_id}/favorites", status_code=201)
async def add_favorite(
    listing_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Объявление не найдено")
    result = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.listing_id == listing_id)
    )
    if result.scalar_one_or_none() is None:
        statement = (
            insert(Favorite)
            .values(user_id=user_id, listing_id=listing_id)
            .on_conflict_do_nothing(constraint="uq_favorite_user_listing")
        )
        await db.execute(statement)
        await db.commit()
    return {"status": "added"}


@app.delete("/catalog/listings/{listing_id}/favorites", status_code=204)
async def remove_favorite(
    listing_id: UUID,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.listing_id == listing_id)
    )
    favorite = result.scalar_one_or_none()
    if favorite:
        await db.delete(favorite)
        await db.commit()
