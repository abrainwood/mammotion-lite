"""Smoke tests for test infrastructure - verify non-obvious fixture behavior."""

from tests.conftest import (
    FakeStatusType,
    FakeSubscription,
    make_event_message,
    make_mock_client,
    make_status_message,
)


def test_fake_subscription_cancel_is_idempotent():
    """Subscription cancel is safe to call multiple times."""
    sub = FakeSubscription()
    assert not sub._cancelled
    sub.cancel()
    assert sub._cancelled
    sub.cancel()  # second call should not raise
    assert sub._cancelled


def test_make_status_message_connected_value():
    """Status factory produces the correct CONNECTED enum value."""
    status = make_status_message(connected=True)
    assert status.params.status.value == FakeStatusType.CONNECTED


def test_make_status_message_disconnected_value():
    """Status factory produces the correct DISCONNECTED enum value."""
    status = make_status_message(connected=False)
    assert status.params.status.value == FakeStatusType.DISCONNECTED


def test_mock_client_login_failure_raises():
    """Mock client with login_succeeds=False raises on login call."""
    import asyncio

    import pytest

    client = make_mock_client(login_succeeds=False)
    assert client.mammotion_http is None
    with pytest.raises(Exception, match="Connection failed"):
        asyncio.get_event_loop().run_until_complete(
            client.login_and_initiate_cloud("user", "pass", None)
        )


def test_make_event_message_without_code_has_no_value():
    """Event factory with no code sets value to None."""
    event = make_event_message(identifier="some_other_event")
    assert event.params.value is None
