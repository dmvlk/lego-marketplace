import httpx

from app.config import settings


class PaymentClient:
    def __init__(self) -> None:
        self.base_url = settings.payment_service_url.rstrip("/")
        self.headers = {"X-Service-Token": settings.service_token}

    async def refund(
        self,
        deal_id: str,
        idempotency_key: str,
        reason: str,
        amount: str | None = None,
    ) -> None:
        payload = {
            "idempotency_key": idempotency_key,
            "reason": reason,
        }
        if amount is not None:
            payload["amount"] = amount
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/payments/deals/{deal_id}/refund",
                headers=self.headers,
                json=payload,
            )
        response.raise_for_status()

    async def release_payout(self, deal_id: str, idempotency_key: str | None = None) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/internal/payments/deals/{deal_id}/payout",
                headers=self.headers,
                json={"idempotency_key": idempotency_key or f"deal-payout-{deal_id}"},
            )
        response.raise_for_status()


payment_client = PaymentClient()
