"""Tests for MammotionLiteData runtime data class and callback dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.mammotion_lite.runtime_data import MammotionLiteData
from tests.conftest import FakeSubscription, make_mock_client, make_snapshot


class TestMammotionLiteData:
    """Test the runtime data container."""

    def _make_data(self, **kwargs) -> MammotionLiteData:
        """Create a MammotionLiteData with sensible defaults."""
        defaults = {
            "client": make_mock_client(),
            "commands": MagicMock(),
            "device_name": "Luba-VSLKJX",
            "iot_id": "abc123",
        }
        defaults.update(kwargs)
        return MammotionLiteData(**defaults)

    def test_initial_state(self):
        """New data has no properties, no snapshot, offline, no reporting."""
        data = self._make_data()
        assert data.properties is None
        assert data.snapshot is None
        assert data.online is False
        assert data.reporting_active is False
        assert data.last_event_code is None
        assert data.last_event_label is None
        assert data.last_event_time is None

    def test_register_and_dispatch_callback(self):
        """Registered callbacks are called on dispatch_update."""
        data = self._make_data()
        called = []
        data.register_update_callback(lambda: called.append(True))
        data.dispatch_update()
        assert len(called) == 1

    def test_multiple_callbacks_all_called(self):
        """All registered callbacks are called."""
        data = self._make_data()
        results = []
        data.register_update_callback(lambda: results.append("a"))
        data.register_update_callback(lambda: results.append("b"))
        data.dispatch_update()
        assert results == ["a", "b"]

    def test_unregister_callback(self):
        """Unregistered callback is not called."""
        data = self._make_data()
        called = []
        unregister = data.register_update_callback(lambda: called.append(True))
        unregister()
        data.dispatch_update()
        assert len(called) == 0

    def test_dispatch_without_callbacks_is_safe(self):
        """dispatch_update with no callbacks doesn't raise."""
        data = self._make_data()
        data.dispatch_update()  # should not raise
