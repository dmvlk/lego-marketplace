from decimal import Decimal

import pytest

from app.fees import calculate_amounts


def test_five_percent_fee_is_deducted_from_seller_payout() -> None:
    amounts = calculate_amounts(Decimal("1000.00"), Decimal("5"))

    assert amounts.buyer_amount == Decimal("1000.00")
    assert amounts.platform_fee == Decimal("50.00")
    assert amounts.seller_payout == Decimal("950.00")


def test_fee_rounds_to_cents() -> None:
    amounts = calculate_amounts(Decimal("10.10"), Decimal("5"))

    assert amounts.platform_fee == Decimal("0.51")


def test_payment_amount_must_be_positive() -> None:
    with pytest.raises(ValueError):
        calculate_amounts(Decimal("0"), Decimal("5"))


def test_fee_cannot_consume_the_entire_payment() -> None:
    with pytest.raises(ValueError):
        calculate_amounts(Decimal("0.01"), Decimal("99"))
