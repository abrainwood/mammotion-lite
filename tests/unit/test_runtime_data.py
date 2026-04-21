"""Tests for MammotionLiteData runtime data class and callback dispatch."""

from __future__ import annotations

from tests.conftest import make_data


class TestMammotionLiteData:
    """Test the runtime data container."""

    def test_initial_state(self):
        """New data has no properties, no snapshot, offline, no reporting."""
        data = make_data()
        assert data.properties is None
        assert data.snapshot is None
        assert data.online is False
        assert data.reporting_active is False
        assert data.last_event_code is None
        assert data.last_event_label is None
        assert data.last_event_time is None

    def test_register_and_dispatch_callback(self):
        """Registered callbacks are called on dispatch_update."""
        data = make_data()
        called = []
        data.register_update_callback(lambda: called.append(True))
        data.dispatch_update()
        assert len(called) == 1

    def test_multiple_callbacks_all_called(self):
        """All registered callbacks are called."""
        data = make_data()
        results = []
        data.register_update_callback(lambda: results.append("a"))
        data.register_update_callback(lambda: results.append("b"))
        data.dispatch_update()
        assert results == ["a", "b"]

    def test_unregister_callback(self):
        """Unregistered callback is not called."""
        data = make_data()
        called = []
        unregister = data.register_update_callback(lambda: called.append(True))
        unregister()
        data.dispatch_update()
        assert len(called) == 0

    def test_dispatch_without_callbacks_is_safe(self):
        """dispatch_update with no callbacks doesn't raise."""
        data = make_data()
        data.dispatch_update()  # should not raise
