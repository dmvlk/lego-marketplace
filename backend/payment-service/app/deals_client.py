import httpx

from app.config import settings


class DealsClient:
    def __init__(self) -> None:
        self.base_url = settings.deals_service_url.rstrip("/")
        self.headers = {"X-Service-Token": settings.service_token}

    async def get_payment_context(self, deal_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/internal/deals/{deal_id}/payment",
                headers=self.headers,
            )
        response.raise_for_status()
        return response.json()

    async def mark_payment_authorized(self, deal_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/deals/{deal_id}/payment-authorized",
                headers=self.headers,
            )
        response.raise_for_status()


deals_client = DealsClient()
