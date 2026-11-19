import asyncio
import logging
import os

import httpx
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)


def safe_websocket_close_code(code: int | None) -> int:
    if code is None or code < 1000 or code in {1004, 1005, 1006, 1015} or 1016 <= code < 3000:
        return 1011
    return code


app = FastAPI(
    title="LEGO Marketplace API Gateway",
    version="0.2.0",
)

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001").rstrip("/")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service:8002").rstrip("/")
DEALS_SERVICE_URL = os.getenv("DEALS_SERVICE_URL", "http://deals-service:8003").rstrip("/")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8004").rstrip("/")
DELIVERY_SERVICE_URL = os.getenv("DELIVERY_SERVICE_URL", "http://delivery-service:8005").rstrip("/")
CHAT_SERVICE_URL = os.getenv("CHAT_SERVICE_URL", "http://chat-service:8006").rstrip("/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "api-gateway",
    }


@app.get("/api/v1")
async def root() -> dict:
    return {
        "name": "LEGO Marketplace",
        "status": "ready",
    }


async def proxy_auth(request: Request, path: str) -> Response:
    headers = {}
    for header in ("authorization", "content-type", "accept"):
        if value := request.headers.get(header):
            headers[header.title()] = value

    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        upstream = await client.request(
            request.method,
            f"{AUTH_SERVICE_URL}{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.post("/api/v1/auth/register")
async def register_proxy(request: Request) -> Response:
    return await proxy_auth(request, "/auth/register")


@app.post("/api/v1/auth/login")
async def login_proxy(request: Request) -> Response:
    return await proxy_auth(request, "/auth/login")


@app.post("/api/v1/auth/refresh")
async def refresh_proxy(request: Request) -> Response:
    return await proxy_auth(request, "/auth/refresh")


@app.post("/api/v1/auth/logout")
async def logout_proxy(request: Request) -> Response:
    return await proxy_auth(request, "/auth/logout")


@app.get("/api/v1/users/me")
async def get_profile_proxy(request: Request) -> Response:
    return await proxy_auth(request, "/users/me")


@app.patch("/api/v1/users/me")
async def update_profile_proxy(request: Request) -> Response:
    return await proxy_auth(request, "/users/me")


async def proxy_catalog(request: Request, path: str) -> Response:
    headers = {}
    for header in ("authorization", "content-type", "accept"):
        if value := request.headers.get(header):
            headers[header.title()] = value
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        upstream = await client.request(
            request.method,
            f"{CATALOG_SERVICE_URL}{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/api/v1/catalog/categories")
async def catalog_categories_proxy(request: Request) -> Response:
    return await proxy_catalog(request, "/catalog/categories")


@app.get("/api/v1/catalog/themes")
async def catalog_themes_proxy(request: Request) -> Response:
    return await proxy_catalog(request, "/catalog/themes")


@app.get("/api/v1/catalog/listings")
async def catalog_listings_proxy(request: Request) -> Response:
    return await proxy_catalog(request, "/catalog/listings")


@app.get("/api/v1/catalog/favorites")
async def catalog_favorites_proxy(request: Request) -> Response:
    return await proxy_catalog(request, "/catalog/favorites")


@app.post("/api/v1/catalog/listings")
async def catalog_create_proxy(request: Request) -> Response:
    return await proxy_catalog(request, "/catalog/listings")


@app.get("/api/v1/catalog/listings/{listing_id}")
async def catalog_detail_proxy(request: Request, listing_id: str) -> Response:
    return await proxy_catalog(request, f"/catalog/listings/{listing_id}")


@app.patch("/api/v1/catalog/listings/{listing_id}")
async def catalog_update_proxy(request: Request, listing_id: str) -> Response:
    return await proxy_catalog(request, f"/catalog/listings/{listing_id}")


@app.delete("/api/v1/catalog/listings/{listing_id}")
async def catalog_archive_proxy(request: Request, listing_id: str) -> Response:
    return await proxy_catalog(request, f"/catalog/listings/{listing_id}")


@app.post("/api/v1/catalog/listings/{listing_id}/favorites")
async def catalog_favorite_add_proxy(request: Request, listing_id: str) -> Response:
    return await proxy_catalog(request, f"/catalog/listings/{listing_id}/favorites")


@app.delete("/api/v1/catalog/listings/{listing_id}/favorites")
async def catalog_favorite_remove_proxy(request: Request, listing_id: str) -> Response:
    return await proxy_catalog(request, f"/catalog/listings/{listing_id}/favorites")


@app.post("/api/v1/catalog/listings/{listing_id}/images")
async def catalog_image_upload_proxy(request: Request, listing_id: str) -> Response:
    return await proxy_catalog(request, f"/catalog/listings/{listing_id}/images")


@app.delete("/api/v1/catalog/listings/{listing_id}/images/{image_id}")
async def catalog_image_remove_proxy(request: Request, listing_id: str, image_id: str) -> Response:
    return await proxy_catalog(request, f"/catalog/listings/{listing_id}/images/{image_id}")


@app.get("/api/v1/catalog/images/{key:path}")
async def catalog_image_proxy(request: Request, key: str) -> Response:
    return await proxy_catalog(request, f"/catalog/images/{key}")


async def proxy_deals(request: Request, path: str) -> Response:
    headers = {}
    for header in ("authorization", "content-type", "accept"):
        if value := request.headers.get(header):
            headers[header.title()] = value
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        upstream = await client.request(
            request.method,
            f"{DEALS_SERVICE_URL}{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/api/v1/offers")
async def deals_list_offers_proxy(request: Request) -> Response:
    return await proxy_deals(request, "/offers")


@app.post("/api/v1/offers")
async def deals_create_offer_proxy(request: Request) -> Response:
    return await proxy_deals(request, "/offers")


@app.post("/api/v1/offers/{offer_id}/counter")
async def deals_counter_offer_proxy(request: Request, offer_id: str) -> Response:
    return await proxy_deals(request, f"/offers/{offer_id}/counter")


@app.post("/api/v1/offers/{offer_id}/reject")
async def deals_reject_offer_proxy(request: Request, offer_id: str) -> Response:
    return await proxy_deals(request, f"/offers/{offer_id}/reject")


@app.post("/api/v1/offers/{offer_id}/accept")
async def deals_accept_offer_proxy(request: Request, offer_id: str) -> Response:
    return await proxy_deals(request, f"/offers/{offer_id}/accept")


@app.post("/api/v1/deals")
async def deals_create_proxy(request: Request) -> Response:
    return await proxy_deals(request, "/deals")


@app.get("/api/v1/deals/purchases")
async def deals_purchases_proxy(request: Request) -> Response:
    return await proxy_deals(request, "/deals/purchases")


@app.get("/api/v1/deals/sales")
async def deals_sales_proxy(request: Request) -> Response:
    return await proxy_deals(request, "/deals/sales")


@app.get("/api/v1/deals/{deal_id}")
async def deals_detail_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_deals(request, f"/deals/{deal_id}")


@app.post("/api/v1/deals/{deal_id}/confirm-offline")
async def deals_confirm_offline_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_deals(request, f"/deals/{deal_id}/confirm-offline")


@app.post("/api/v1/deals/{deal_id}/cancel")
async def deals_cancel_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_deals(request, f"/deals/{deal_id}/cancel")


@app.post("/api/v1/deals/{deal_id}/inspection/confirm")
async def deals_inspection_confirm_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_deals(request, f"/deals/{deal_id}/inspection/confirm")


@app.post("/api/v1/deals/{deal_id}/disputes")
async def disputes_open_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_deals(request, f"/deals/{deal_id}/disputes")


@app.get("/api/v1/disputes/{dispute_id}")
async def disputes_detail_proxy(request: Request, dispute_id: str) -> Response:
    return await proxy_deals(request, f"/disputes/{dispute_id}")


@app.post("/api/v1/disputes/{dispute_id}/evidence")
async def disputes_evidence_proxy(request: Request, dispute_id: str) -> Response:
    return await proxy_deals(request, f"/disputes/{dispute_id}/evidence")


@app.post("/api/v1/disputes/{dispute_id}/evidence/images")
async def disputes_evidence_image_upload_proxy(request: Request, dispute_id: str) -> Response:
    return await proxy_deals(request, f"/disputes/{dispute_id}/evidence/images")


@app.get("/api/v1/disputes/{dispute_id}/evidence/{evidence_id}/image")
async def disputes_evidence_image_proxy(
    request: Request,
    dispute_id: str,
    evidence_id: str,
) -> Response:
    return await proxy_deals(
        request,
        f"/disputes/{dispute_id}/evidence/{evidence_id}/image",
    )


@app.get("/api/v1/admin/disputes")
async def disputes_admin_list_proxy(request: Request) -> Response:
    return await proxy_deals(request, "/admin/disputes")


@app.get("/api/v1/admin/disputes/{dispute_id}/audit")
async def disputes_admin_audit_proxy(request: Request, dispute_id: str) -> Response:
    return await proxy_deals(request, f"/admin/disputes/{dispute_id}/audit")


@app.post("/api/v1/admin/disputes/{dispute_id}/request-evidence")
async def disputes_admin_request_evidence_proxy(request: Request, dispute_id: str) -> Response:
    return await proxy_deals(request, f"/admin/disputes/{dispute_id}/request-evidence")


@app.post("/api/v1/admin/disputes/{dispute_id}/resolve")
async def disputes_admin_resolve_proxy(request: Request, dispute_id: str) -> Response:
    return await proxy_deals(request, f"/admin/disputes/{dispute_id}/resolve")


async def proxy_payments(request: Request, path: str) -> Response:
    headers = {}
    for header in (
        "authorization",
        "content-type",
        "accept",
        "idempotency-key",
        "x-provider-signature",
    ):
        if value := request.headers.get(header):
            headers[header.title()] = value
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        upstream = await client.request(
            request.method,
            f"{PAYMENT_SERVICE_URL}{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.post("/api/v1/payments/deals/{deal_id}")
async def payments_start_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_payments(request, f"/payments/deals/{deal_id}")


@app.post("/api/v1/payments/webhooks/{provider_name}")
async def payments_webhook_proxy(request: Request, provider_name: str) -> Response:
    return await proxy_payments(request, f"/payments/webhooks/{provider_name}")


@app.get("/api/v1/payments/{payment_id}")
async def payments_get_proxy(request: Request, payment_id: str) -> Response:
    return await proxy_payments(request, f"/payments/{payment_id}")


async def proxy_delivery(request: Request, path: str) -> Response:
    headers = {}
    for header in ("authorization", "content-type", "accept"):
        if value := request.headers.get(header):
            headers[header.title()] = value
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        upstream = await client.request(
            request.method,
            f"{DELIVERY_SERVICE_URL}{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.post("/api/v1/deliveries/deals/{deal_id}/ship")
async def delivery_ship_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_delivery(request, f"/deliveries/deals/{deal_id}/ship")


@app.get("/api/v1/deliveries/deals/{deal_id}")
async def delivery_get_by_deal_proxy(request: Request, deal_id: str) -> Response:
    return await proxy_delivery(request, f"/deliveries/deals/{deal_id}")


@app.get("/api/v1/deliveries/{shipment_id}")
async def delivery_get_proxy(request: Request, shipment_id: str) -> Response:
    return await proxy_delivery(request, f"/deliveries/{shipment_id}")


@app.patch("/api/v1/deliveries/{shipment_id}/tracking")
async def delivery_tracking_proxy(request: Request, shipment_id: str) -> Response:
    return await proxy_delivery(request, f"/deliveries/{shipment_id}/tracking")


@app.post("/api/v1/deliveries/{shipment_id}/delivered")
async def delivery_delivered_proxy(request: Request, shipment_id: str) -> Response:
    return await proxy_delivery(request, f"/deliveries/{shipment_id}/delivered")


async def proxy_chat(request: Request, path: str) -> Response:
    headers = {}
    for header in ("authorization", "content-type", "accept"):
        if value := request.headers.get(header):
            headers[header.title()] = value
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        upstream = await client.request(
            request.method,
            f"{CHAT_SERVICE_URL}{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/api/v1/conversations")
async def chat_list_conversations_proxy(request: Request) -> Response:
    return await proxy_chat(request, "/conversations")


@app.post("/api/v1/conversations")
async def chat_create_conversation_proxy(request: Request) -> Response:
    return await proxy_chat(request, "/conversations")


@app.get("/api/v1/conversations/{conversation_id}/messages")
async def chat_list_messages_proxy(request: Request, conversation_id: str) -> Response:
    return await proxy_chat(request, f"/conversations/{conversation_id}/messages")


@app.post("/api/v1/conversations/{conversation_id}/messages")
async def chat_send_message_proxy(request: Request, conversation_id: str) -> Response:
    return await proxy_chat(request, f"/conversations/{conversation_id}/messages")


@app.websocket("/api/v1/ws/conversations/{conversation_id}")
async def chat_websocket_proxy(websocket: WebSocket, conversation_id: str) -> None:
    websocket_base_url = (
        CHAT_SERVICE_URL.replace("https://", "wss://", 1)
        .replace("http://", "ws://", 1)
    )
    upstream_url = f"{websocket_base_url}/ws/conversations/{conversation_id}"
    try:
        async with connect(upstream_url, open_timeout=10, close_timeout=2) as upstream:
            await websocket.accept()

            async def forward_to_chat() -> None:
                while True:
                    await upstream.send(await websocket.receive_text())

            async def forward_to_browser() -> None:
                try:
                    async for message in upstream:
                        await websocket.send_text(message)
                finally:
                    if (
                        websocket.application_state == WebSocketState.CONNECTED
                        and websocket.client_state == WebSocketState.CONNECTED
                    ):
                        await websocket.close(
                            code=safe_websocket_close_code(upstream.close_code),
                            reason=(upstream.close_reason or "")[:123],
                        )

            tasks = {
                asyncio.create_task(forward_to_chat()),
                asyncio.create_task(forward_to_browser()),
            }
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except ConnectionClosed as error:
        if (
            websocket.application_state == WebSocketState.CONNECTED
            and websocket.client_state == WebSocketState.CONNECTED
        ):
            close_frame = error.rcvd
            await websocket.close(
                code=safe_websocket_close_code(close_frame.code if close_frame else None),
                reason=(close_frame.reason if close_frame else "")[:123],
            )
    except (OSError, WebSocketException):
        logger.exception("Could not proxy chat WebSocket")
        if (
            websocket.application_state == WebSocketState.CONNECTED
            and websocket.client_state == WebSocketState.CONNECTED
        ):
            await websocket.close(code=1011, reason="Chat service unavailable")
