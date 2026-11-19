from app.models import DealStatus, TransactionType
from app.rules import can_cancel, initial_status, offline_complete


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
