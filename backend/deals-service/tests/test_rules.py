from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import DealStatus, DisputeDecision, TransactionType
from app.rules import add_business_days, can_cancel, initial_status, offline_complete
from app.schemas import DisputeResolve


def test_offline_and_protected_deals_start_in_different_states() -> None:
    assert initial_status(TransactionType.OFFLINE) == DealStatus.PENDING_CONFIRMATION
    assert initial_status(TransactionType.ONLINE_PROTECTED) == DealStatus.AWAITING_PAYMENT


def test_only_uncompleted_deals_can_be_cancelled() -> None:
    assert can_cancel(DealStatus.PENDING_CONFIRMATION)
    assert can_cancel(DealStatus.AWAITING_PAYMENT)
    assert not can_cancel(DealStatus.COMPLETED)
    assert not can_cancel(DealStatus.CANCELLED)


def test_offline_deal_requires_confirmation_from_both_parties() -> None:
    assert not offline_complete(True, False)
    assert not offline_complete(False, True)
    assert offline_complete(True, True)


def test_dispute_deadline_skips_weekends() -> None:
    start = datetime(2026, 1, 2, 15, 30)

    assert add_business_days(start, 2) == datetime(2026, 1, 6, 15, 30)


def test_partial_refund_requires_a_positive_amount() -> None:
    resolution = DisputeResolve(
        decision=DisputeDecision.PARTIAL_REFUND,
        refund_amount=Decimal("12.50"),
        note="Частичное возмещение",
    )
    assert resolution.refund_amount == Decimal("12.50")

    with pytest.raises(ValidationError):
        DisputeResolve(decision=DisputeDecision.PARTIAL_REFUND, note="Возмещение")
