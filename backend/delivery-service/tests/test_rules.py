from app.models import ShipmentStatus
from app.rules import can_confirm_delivery, can_update_tracking


def test_tracking_statuses_follow_allowed_transitions() -> None:
    assert can_update_tracking(
        ShipmentStatus.CREATED,
        ShipmentStatus.IN_TRANSIT,
        "TRACK-123",
        None,
    )
    assert not can_update_tracking(
        ShipmentStatus.CREATED,
        ShipmentStatus.DELIVERED,
        "TRACK-123",
        None,
    )
    assert not can_update_tracking(
        ShipmentStatus.RETURNED,
        ShipmentStatus.IN_TRANSIT,
        "TRACK-123",
        "TRACK-123",
    )


def test_delivery_requires_tracking_and_an_in_transit_state() -> None:
    assert can_confirm_delivery(ShipmentStatus.IN_TRANSIT, "TRACK-123")
    assert can_confirm_delivery(ShipmentStatus.OUT_FOR_DELIVERY, "TRACK-123")
    assert not can_confirm_delivery(ShipmentStatus.CREATED, "TRACK-123")
    assert not can_confirm_delivery(ShipmentStatus.IN_TRANSIT, None)
