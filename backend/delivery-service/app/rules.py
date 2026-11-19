from app.models import ShipmentStatus


ALLOWED_TRACKING_TRANSITIONS = {
    ShipmentStatus.CREATED: {ShipmentStatus.IN_TRANSIT, ShipmentStatus.EXCEPTION},
    ShipmentStatus.IN_TRANSIT: {
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.EXCEPTION,
        ShipmentStatus.RETURNED,
    },
    ShipmentStatus.OUT_FOR_DELIVERY: {
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.EXCEPTION,
        ShipmentStatus.RETURNED,
    },
    ShipmentStatus.EXCEPTION: {
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.RETURNED,
    },
    ShipmentStatus.RETURNED: set(),
    ShipmentStatus.DELIVERED: set(),
}


def can_update_tracking(
    current: ShipmentStatus,
    new_status: ShipmentStatus | None,
    tracking_number: str | None,
    current_tracking_number: str | None,
) -> bool:
    if current in {ShipmentStatus.RETURNED, ShipmentStatus.DELIVERED}:
        return False
    if new_status is not None and new_status != current:
        if new_status == ShipmentStatus.DELIVERED:
            return False
        if new_status not in ALLOWED_TRACKING_TRANSITIONS[current]:
            return False
    effective_tracking_number = tracking_number or current_tracking_number
    if new_status in {
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.EXCEPTION,
        ShipmentStatus.RETURNED,
    } and not effective_tracking_number:
        return False
    return True


def can_confirm_delivery(status: ShipmentStatus, tracking_number: str | None) -> bool:
    return status in {
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.EXCEPTION,
    } and bool(tracking_number)
