from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


@dataclass(frozen=True)
class PaymentAmounts:
    buyer_amount: Decimal
    platform_fee: Decimal
    seller_payout: Decimal


def calculate_amounts(amount: Decimal, fee_percent: Decimal) -> PaymentAmounts:
    if amount <= 0:
        raise ValueError("Сумма платежа должна быть больше нуля")
    if fee_percent < 0 or fee_percent >= 100:
        raise ValueError("Комиссия должна быть от 0 до 100 процентов")

    buyer_amount = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    platform_fee = (buyer_amount * fee_percent / Decimal("100")).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )
    if platform_fee >= buyer_amount:
        raise ValueError("Комиссия не может быть равна сумме платежа")
    return PaymentAmounts(
        buyer_amount=buyer_amount,
        platform_fee=platform_fee,
        seller_payout=buyer_amount - platform_fee,
    )
