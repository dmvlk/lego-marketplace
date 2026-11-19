import os

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="LEGO Marketplace API Gateway",
    version="0.2.0",
)

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001").rstrip("/")

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
    authorization = request.headers.get("authorization")
    if authorization:
        headers["Authorization"] = authorization

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
