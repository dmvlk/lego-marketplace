from app.models import DealStatus, TransactionType


def initial_status(transaction_type: TransactionType) -> DealStatus:
    if transaction_type == TransactionType.OFFLINE:
        return DealStatus.PENDING_CONFIRMATION
    return DealStatus.AWAITING_PAYMENT


def can_cancel(status: DealStatus) -> bool:
    return status in {DealStatus.PENDING_CONFIRMATION, DealStatus.AWAITING_PAYMENT}


def offline_complete(buyer_confirmed: bool, seller_confirmed: bool) -> bool:
    return buyer_confirmed and seller_confirmed
