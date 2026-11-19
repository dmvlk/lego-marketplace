import os

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="LEGO Marketplace API Gateway",
    version="0.2.0",
)

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001").rstrip("/")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service:8002").rstrip("/")
DEALS_SERVICE_URL = os.getenv("DEALS_SERVICE_URL", "http://deals-service:8003").rstrip("/")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8004").rstrip("/")

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
