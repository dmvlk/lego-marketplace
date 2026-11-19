import httpx

from app.config import settings


class PaymentClient:
    def __init__(self) -> None:
        self.base_url = settings.payment_service_url.rstrip("/")
        self.headers = {"X-Service-Token": settings.service_token}

    async def release_payout(self, deal_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/payments/deals/{deal_id}/payout",
                headers=self.headers,
                json={"idempotency_key": f"deal-payout-{deal_id}"},
            )
        response.raise_for_status()


payment_client = PaymentClient()
