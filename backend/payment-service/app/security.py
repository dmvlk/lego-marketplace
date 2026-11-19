import hmac
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, status

from app.config import settings


async def get_user_id(authorization: Annotated[str | None, Header()] = None) -> UUID:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    try:
        payload = jwt.decode(
            authorization.removeprefix("Bearer ").strip(),
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    try:
        return UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")


def require_service_token(service_token: str | None) -> None:
    if not service_token or not hmac.compare_digest(service_token, settings.service_token):
        raise HTTPException(status_code=401, detail="Недействительный сервисный токен")
