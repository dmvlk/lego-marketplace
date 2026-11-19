from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, status

from app.config import settings


def decode_access_token(token: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as error:
        raise ValueError("Invalid access token") from error
    if payload.get("type") != "access":
        raise ValueError("Invalid access token")
    try:
        return UUID(payload["sub"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid access token") from error


async def get_user_id(authorization: Annotated[str | None, Header()] = None) -> UUID:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    try:
        return decode_access_token(authorization.removeprefix("Bearer ").strip())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
