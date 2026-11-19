import hashlib
import hmac
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.config import settings


@dataclass(frozen=True)
class AuthorizationEvent:
    event_id: str
    event_type: str
    payment_id: uuid.UUID
    provider_reference: str
    amount: Decimal
    currency: str


class PaymentProvider(Protocol):
    name: str

    async def authorize(
        self,
        payment_id: uuid.UUID,
        amount: Decimal,
        currency: str,
    ) -> AuthorizationEvent: ...

    async def refund(self, payment_id: uuid.UUID, idempotency_key: str) -> str: ...

    async def payout(self, payment_id: uuid.UUID, idempotency_key: str) -> str: ...

    def verify_webhook(self, body: bytes, signature: str | None) -> bool: ...


class MockProvider:
    name = "mock"

    async def authorize(
        self,
        payment_id: uuid.UUID,
        amount: Decimal,
        currency: str,
    ) -> AuthorizationEvent:
        return AuthorizationEvent(
            event_id=f"mock-authorized-{payment_id}",
            event_type="payment.authorized",
            payment_id=payment_id,
            provider_reference=f"mock-payment-{payment_id}",
            amount=amount,
            currency=currency,
        )

    async def refund(self, payment_id: uuid.UUID, idempotency_key: str) -> str:
        return f"mock-refund-{self._key(payment_id, idempotency_key)}"

    async def payout(self, payment_id: uuid.UUID, idempotency_key: str) -> str:
        return f"mock-payout-{self._key(payment_id, idempotency_key)}"

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        expected = hmac.new(
            settings.payment_webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature.lower())

    @staticmethod
    def _key(payment_id: uuid.UUID, idempotency_key: str) -> str:
        value = f"{payment_id}:{idempotency_key}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()[:32]


provider: PaymentProvider = MockProvider()
