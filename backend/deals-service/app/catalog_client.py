import httpx

from app.config import settings


class CatalogClient:
    def __init__(self) -> None:
        self.base_url = settings.catalog_service_url.rstrip("/")
        self.headers = {"X-Service-Token": settings.service_token}

    async def get_listing(self, listing_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/internal/listings/{listing_id}",
                headers=self.headers,
            )
        response.raise_for_status()
        return response.json()

    async def reserve(self, listing_id: str, deal_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/listings/{listing_id}/reserve",
                params={"deal_id": deal_id},
                headers=self.headers,
            )
        response.raise_for_status()

    async def release(self, listing_id: str, deal_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/listings/{listing_id}/release",
                params={"deal_id": deal_id},
                headers=self.headers,
            )
        response.raise_for_status()

    async def mark_sold(self, listing_id: str, deal_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/listings/{listing_id}/sold",
                params={"deal_id": deal_id},
                headers=self.headers,
            )
        response.raise_for_status()


catalog_client = CatalogClient()
