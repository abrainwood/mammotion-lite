"""Smoke test to verify test infrastructure works."""

from tests.conftest import (
    make_event_message,
    make_mock_client,
    make_properties_message,
    make_snapshot,
    make_status_message,
)


def test_mock_client_has_expected_methods(mock_client):
    """Mock client exposes the pymammotion API surface we need."""
    assert mock_client.mower("anything") is not None
    assert mock_client.subscribe_device_properties is not None
    assert mock_client.subscribe_device_status is not None
    assert mock_client.subscribe_device_event is not None


def test_make_snapshot_defaults():
    """Snapshot factory produces sensible defaults."""
    snap = make_snapshot()
    assert snap.battery_level == 80
    assert snap.mowing_activity == "mowing"
    assert snap.blade_height == 50
    assert snap.online is True


def test_make_snapshot_custom_area():
    """Snapshot factory accepts custom area for progress testing."""
    # 42% progress encoded in upper 16 bits
    area = 42 << 16
    snap = make_snapshot(area=area)
    assert snap.raw.report_data.work.area >> 16 == 42


def test_make_properties_message():
    """Properties factory builds message with expected fields."""
    props = make_properties_message(battery=85, knife_height=40)
    assert props.params.items.batteryPercentage.value == 85
    assert props.params.items.knifeHeight.value == 40
    assert props.params.items.deviceState is None  # not set


def test_make_event_message_with_code():
    """Event factory builds notification event with JSON code."""
    import json

    event = make_event_message(code="1301")
    assert event.params.identifier == "device_notification_event"
    data = json.loads(event.params.value.data)
    assert data["code"] == "1301"


def test_make_event_message_without_code():
    """Event factory with no code produces event with no value."""
    event = make_event_message(identifier="some_other_event")
    assert event.params.value is None


def test_make_status_message_connected():
    """Status factory builds connected message."""
    status = make_status_message(connected=True)
    assert status.params.status.value is not None


def test_mock_client_login_failure():
    """Mock client can simulate login failure."""
    import pytest

    client = make_mock_client(login_succeeds=False)
    assert client.mammotion_http is None
    with pytest.raises(Exception, match="Connection failed"):
        # This is an AsyncMock - call it to trigger the side_effect
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            client.login_and_initiate_cloud("user", "pass", None)
        )


def test_fake_subscription_cancel():
    """Subscription can be cancelled."""
    from tests.conftest import FakeSubscription

    sub = FakeSubscription()
    assert not sub._cancelled
    sub.cancel()
    assert sub._cancelled
