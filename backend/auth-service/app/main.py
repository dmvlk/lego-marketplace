from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import AccountStatus, RefreshToken, Role, RoleName, User
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UpdateProfileRequest, UserResponse
from app.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

app = FastAPI(title="LEGO Marketplace Auth Service", version="0.3.0")


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_reference=user.avatar_reference,
        status=user.status.value,
        role=user.role.name.value,
        created_at=user.created_at,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "auth"}


@app.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь уже зарегистрирован")

    role_result = await db.execute(select(Role).where(Role.name == RoleName.USER))
    role = role_result.scalar_one_or_none()
    if role is None:
        role = Role(name=RoleName.USER)
        db.add(role)
        await db.flush()

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role_id=role.id,
        status=AccountStatus.ACTIVE,
    )
    db.add(user)
    await db.flush()

    refresh_token = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_days),
        )
    )
    await db.commit()
    await db.refresh(user)
    user.role = role
    return TokenResponse(
        access_token=create_access_token(user.id, role.name.value),
        refresh_token=refresh_token,
    )


@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if user.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Аккаунт недоступен")

    refresh_token = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_days),
        )
    )
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.name.value),
        refresh_token=refresh_token,
    )


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken)
        .options(selectinload(RefreshToken.user).selectinload(User.role))
        .where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if (
        stored is None
        or stored.revoked_at is not None
        or stored.expires_at <= datetime.now(timezone.utc)
        or stored.user.status != AccountStatus.ACTIVE
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный refresh-токен")

    stored.revoked_at = datetime.now(timezone.utc)
    replacement = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=stored.user_id,
            token_hash=hash_refresh_token(replacement),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_days),
        )
    )
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(stored.user_id, stored.user.role.name.value),
        refresh_token=replacement,
    )


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(payload.refresh_token))
    )
    stored = result.scalar_one_or_none()
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        await db.commit()


@app.get("/users/me", response_model=UserResponse)
async def get_profile(user: User = Depends(get_current_user)):
    return user_response(user)


@app.patch("/users/me", response_model=UserResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.avatar_reference is not None:
        user.avatar_reference = payload.avatar_reference
    await db.commit()
    await db.refresh(user)
    return user_response(user)
