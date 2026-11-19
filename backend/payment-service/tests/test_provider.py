import asyncio
import hashlib
import hmac
import uuid
from decimal import Decimal

from app.config import settings
from app.provider import MockProvider


def test_mock_provider_signatures_are_verified() -> None:
    mock_provider = MockProvider()
    body = b'{"event_id":"test-event"}'
    signature = hmac.new(
        settings.payment_webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    assert mock_provider.verify_webhook(body, signature)
    assert not mock_provider.verify_webhook(body, "invalid")


def test_mock_authorization_has_no_real_provider_reference() -> None:
    payment_id = uuid.uuid4()
    event = asyncio.run(
        MockProvider().authorize(payment_id, Decimal("10.00"), "RUB")
    )

    assert event.event_type == "payment.authorized"
    assert event.provider_reference == f"mock-payment-{payment_id}"
