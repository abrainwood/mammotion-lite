"""Tests for mammotion_lite binary sensor."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.mammotion_lite.runtime_data import MammotionLiteData
from tests.conftest import make_mock_client


def _make_data(**kwargs) -> MammotionLiteData:
    defaults = {
        "client": make_mock_client(),
        "commands": MagicMock(),
        "device_name": "Luba-VSLKJX",
        "iot_id": "abc123",
    }
    defaults.update(kwargs)
    return MammotionLiteData(**defaults)


class TestOnlineStatus:
    """Test online/offline binary sensor logic."""

    def test_initially_offline(self):
        """New data defaults to offline."""
        data = _make_data()
        assert data.online is False

    def test_online_after_status_push(self):
        """Setting online=True makes the sensor report on."""
        data = _make_data()
        data.online = True
        assert data.online is True

    def test_offline_after_status_push(self):
        """Setting online=False makes the sensor report off."""
        data = _make_data()
        data.online = True
        data.online = False
        assert data.online is False
