import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog_client import catalog_client
from app.database import SessionFactory, get_db
from app.models import Conversation, ConversationParticipant, Message
from app.schemas import ConversationCreate, ConversationResponse, MessageCreate, MessageResponse
from app.security import decode_access_token, get_user_id

logger = logging.getLogger(__name__)
app = FastAPI(title="LEGO Marketplace Chat Service", version="0.5.0")


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[UUID, set[WebSocket]] = {}

    async def connect(self, conversation_id: UUID, websocket: WebSocket) -> None:
        self.connections.setdefault(conversation_id, set()).add(websocket)

    def disconnect(self, conversation_id: UUID, websocket: WebSocket) -> None:
        connections = self.connections.get(conversation_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self.connections.pop(conversation_id, None)

    async def broadcast(self, conversation_id: UUID, event: dict) -> None:
        for websocket in tuple(self.connections.get(conversation_id, set())):
            try:
                await websocket.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                logger.info("Removing a closed WebSocket from conversation %s", conversation_id)
                self.disconnect(conversation_id, websocket)


connection_manager = ConnectionManager()


async def fetch_listing_context(listing_id: UUID) -> dict:
    try:
        return await catalog_client.get_listing(str(listing_id))
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        logger.error("Catalog returned %s while opening a conversation", error.response.status_code)
        raise HTTPException(status_code=502, detail="Не удалось проверить объявление")
    except httpx.RequestError:
        logger.exception("Catalog service is unavailable while opening a conversation")
        raise HTTPException(status_code=503, detail="Сервис каталога временно недоступен")


async def find_conversation(
    db: AsyncSession,
    listing_id: UUID,
    buyer_id: UUID,
) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.listing_id == listing_id,
            Conversation.buyer_id == buyer_id,
        )
    )
    return result.scalar_one_or_none()


async def unread_message_count(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
) -> int:
    result = await db.execute(
        select(func.count(Message.id))
        .join(
            ConversationParticipant,
            and_(
                ConversationParticipant.conversation_id == Message.conversation_id,
                ConversationParticipant.user_id == user_id,
            ),
        )
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_id != user_id,
            or_(
                ConversationParticipant.last_read_at.is_(None),
                Message.created_at > ConversationParticipant.last_read_at,
            ),
        )
    )
    return result.scalar_one()


async def require_participant(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    participant = await db.get(ConversationParticipant, (conversation_id, user_id))
    if participant is None:
        raise HTTPException(status_code=403, detail="Нет доступа к этому диалогу")
    return conversation


async def save_message(
    db: AsyncSession,
    conversation: Conversation,
    sender_id: UUID,
    payload: MessageCreate,
) -> Message:
    message = Message(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        sender_id=sender_id,
        content=payload.content,
    )
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


def conversation_response(
    conversation: Conversation,
    unread_count: int = 0,
) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        listing_id=conversation.listing_id,
        buyer_id=conversation.buyer_id,
        seller_id=conversation.seller_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        unread_count=unread_count,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "chat"}


@app.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    statement = (
        select(Conversation, func.count(Message.id).label("unread_count"))
        .join(
            ConversationParticipant,
            ConversationParticipant.conversation_id == Conversation.id,
        )
        .outerjoin(
            Message,
            and_(
                Message.conversation_id == Conversation.id,
                Message.sender_id != user_id,
                or_(
                    ConversationParticipant.last_read_at.is_(None),
                    Message.created_at > ConversationParticipant.last_read_at,
                ),
            ),
        )
        .where(ConversationParticipant.user_id == user_id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(statement)
    return [
        conversation_response(conversation, unread_count)
        for conversation, unread_count in result.all()
    ]


@app.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    payload: ConversationCreate,
    response: Response,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    listing = await fetch_listing_context(payload.listing_id)
    seller_id = UUID(str(listing["seller_id"]))
    if seller_id == user_id:
        raise HTTPException(status_code=403, detail="Нельзя открыть диалог с самим собой")

    existing = await find_conversation(db, payload.listing_id, user_id)
    if existing is not None:
        response.status_code = 200
        return conversation_response(
            existing,
            await unread_message_count(db, existing.id, user_id),
        )
    if listing["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Новое обсуждение доступно только для активного объявления")

    now = datetime.now(timezone.utc)
    conversation = Conversation(
        id=uuid.uuid4(),
        listing_id=payload.listing_id,
        buyer_id=user_id,
        seller_id=seller_id,
        participants=[
            ConversationParticipant(user_id=user_id, role="buyer", last_read_at=now),
            ConversationParticipant(user_id=seller_id, role="seller", last_read_at=now),
        ],
    )
    db.add(conversation)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await find_conversation(db, payload.listing_id, user_id)
        if existing is None:
            raise HTTPException(status_code=409, detail="Не удалось создать диалог")
        response.status_code = 200
        return conversation_response(
            existing,
            await unread_message_count(db, existing.id, user_id),
        )

    response.status_code = 201
    return conversation_response(conversation)


@app.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    await require_participant(db, conversation_id, user_id)
    participant = await db.get(ConversationParticipant, (conversation_id, user_id))
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    messages = result.scalars().all()
    if messages:
        participant.last_read_at = messages[-1].created_at
        await db.commit()
    return messages


@app.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=201,
)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    user_id: UUID = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    conversation = await require_participant(db, conversation_id, user_id)
    message = await save_message(db, conversation, user_id, payload)
    response = MessageResponse.model_validate(message)
    await connection_manager.broadcast(
        conversation_id,
        {"type": "message", "message": response.model_dump(mode="json")},
    )
    return response


@app.websocket("/ws/conversations/{conversation_id}")
async def conversation_websocket(websocket: WebSocket, conversation_id: UUID):
    await websocket.accept()
    connected = False
    try:
        try:
            first_frame = await asyncio.wait_for(websocket.receive_text(), timeout=10)
            auth_message = json.loads(first_frame)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            await websocket.close(code=4401, reason="Authentication required")
            return
        if (
            not isinstance(auth_message, dict)
            or auth_message.get("type") != "authenticate"
            or not isinstance(auth_message.get("access_token"), str)
        ):
            await websocket.close(code=4401, reason="Authentication required")
            return
        try:
            user_id = decode_access_token(auth_message["access_token"])
        except ValueError:
            await websocket.close(code=4401, reason="Invalid access token")
            return

        async with SessionFactory() as db:
            participant = await db.get(
                ConversationParticipant,
                (conversation_id, user_id),
            )
        if participant is None:
            await websocket.close(code=4403, reason="Not a conversation participant")
            return

        await connection_manager.connect(conversation_id, websocket)
        connected = True
        await websocket.send_json({"type": "authenticated"})
        while True:
            raw_message = await websocket.receive_text()
            try:
                payload = MessageCreate.model_validate_json(raw_message)
            except ValidationError:
                await websocket.send_json({"type": "error", "detail": "Некорректное сообщение"})
                continue
            async with SessionFactory() as db:
                conversation = await require_participant(db, conversation_id, user_id)
                message = await save_message(db, conversation, user_id, payload)
            response = MessageResponse.model_validate(message)
            await connection_manager.broadcast(
                conversation_id,
                {"type": "message", "message": response.model_dump(mode="json")},
            )
    except WebSocketDisconnect:
        pass
    except SQLAlchemyError:
        logger.exception("Chat WebSocket database operation failed")
        await websocket.close(code=1011, reason="Database operation failed")
    finally:
        if connected:
            connection_manager.disconnect(conversation_id, websocket)
