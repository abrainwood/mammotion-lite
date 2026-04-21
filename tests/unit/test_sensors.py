"""Tests for mammotion_lite sensor value extraction functions."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from custom_components.mammotion_lite.const import EVENT_CODE_LABELS
from tests.conftest import (
    make_data,
    make_properties_message,
    make_snapshot,
)


class TestGetBattery:
    """Test battery value extraction with fallback chain."""

    def test_battery_from_snapshot_preferred(self):
        """Snapshot battery_level is preferred when > 0."""
        from custom_components.mammotion_lite.sensors import get_battery

        data = make_data()
        data.snapshot = make_snapshot(battery_level=85)
        data.properties = make_properties_message(battery=70)
        assert get_battery(data) == 85

    def test_battery_from_properties_fallback(self):
        """Properties battery used when no snapshot."""
        from custom_components.mammotion_lite.sensors import get_battery

        data = make_data()
        data.properties = make_properties_message(battery=70)
        assert get_battery(data) == 70

    def test_battery_none_when_no_data(self):
        """Returns None when neither snapshot nor properties have battery."""
        from custom_components.mammotion_lite.sensors import get_battery

        data = make_data()
        assert get_battery(data) is None

    def test_battery_falls_through_zero_snapshot(self):
        """Snapshot with battery_level=0 falls through to properties."""
        from custom_components.mammotion_lite.sensors import get_battery

        data = make_data()
        data.snapshot = make_snapshot(battery_level=0)
        data.properties = make_properties_message(battery=65)
        assert get_battery(data) == 65


class TestGetActivity:
    """Test activity value extraction with fallback chain."""

    def test_activity_from_snapshot_preferred(self):
        """Snapshot mowing_activity is preferred when not unknown(0)."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.snapshot = make_snapshot(mowing_activity="mowing")
        assert get_activity(data) == "mowing"

    def test_activity_fallback_to_last_event(self):
        """Falls back to EVENT_CODE_LABELS lookup when snapshot is unknown."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.snapshot = make_snapshot(mowing_activity="unknown(0)")
        data.last_event_code = "1307"
        # get_activity derives the label from EVENT_CODE_LABELS, not from last_event_label
        assert get_activity(data) == EVENT_CODE_LABELS["1307"]

    def test_activity_fallback_to_device_state(self):
        """Falls back to properties deviceState when no event."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.properties = make_properties_message(device_state="standby")
        assert get_activity(data) == "standby"

    def test_activity_none_when_no_data(self):
        """Returns None when no data sources available."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        assert get_activity(data) is None


class TestGetProgress:
    """Test job progress extraction from packed area field."""

    def test_progress_from_area_upper_16_bits(self):
        """Progress percentage is area >> 16."""
        from custom_components.mammotion_lite.sensors import get_progress

        data = make_data()
        # 42% encoded in upper 16 bits
        data.snapshot = make_snapshot(area=42 << 16)
        assert get_progress(data) == 42

    def test_progress_100_percent(self):
        """100% progress."""
        from custom_components.mammotion_lite.sensors import get_progress

        data = make_data()
        data.snapshot = make_snapshot(area=100 << 16)
        assert get_progress(data) == 100

    def test_progress_none_when_no_snapshot(self):
        """Returns None when no snapshot."""
        from custom_components.mammotion_lite.sensors import get_progress

        data = make_data()
        assert get_progress(data) is None

    def test_progress_none_when_area_zero(self):
        """Returns None when area is 0 (no job data)."""
        from custom_components.mammotion_lite.sensors import get_progress

        data = make_data()
        data.snapshot = make_snapshot(area=0)
        assert get_progress(data) is None


class TestGetLastEvent:
    """Test last event label extraction."""

    def test_returns_label_when_set(self):
        """Returns last event label."""
        from custom_components.mammotion_lite.sensors import get_last_event

        data = make_data()
        data.last_event_label = "Task started"
        assert get_last_event(data) == "Task started"

    def test_returns_none_when_no_event(self):
        """Returns None when no event received."""
        from custom_components.mammotion_lite.sensors import get_last_event

        data = make_data()
        assert get_last_event(data) is None

    def test_extra_attrs_include_code_and_timestamp(self):
        """Extra attributes include code and ISO timestamp."""
        from custom_components.mammotion_lite.sensors import get_last_event_attrs

        data = make_data()
        data.last_event_code = "1301"
        data.last_event_time = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc)
        attrs = get_last_event_attrs(data)
        assert attrs["code"] == "1301"
        assert "2026-04-20" in attrs["timestamp"]

    def test_extra_attrs_empty_when_no_event(self):
        """Extra attributes are empty when no event."""
        from custom_components.mammotion_lite.sensors import get_last_event_attrs

        data = make_data()
        assert get_last_event_attrs(data) == {}


class TestExtractWifiRssi:
    """Test WiFi RSSI extraction from networkInfo property."""

    def test_rssi_from_json_string(self):
        """Extracts wifi_rssi from JSON string networkInfo."""
        from custom_components.mammotion_lite.sensors import extract_wifi_rssi

        data = make_data()
        data.properties = make_properties_message(network_info={"wifi_rssi": -55})
        assert extract_wifi_rssi(data) == -55

    def test_rssi_none_when_no_properties(self):
        """Returns None when no properties."""
        from custom_components.mammotion_lite.sensors import extract_wifi_rssi

        data = make_data()
        assert extract_wifi_rssi(data) is None

    def test_rssi_none_when_no_network_info(self):
        """Returns None when networkInfo not in properties."""
        from custom_components.mammotion_lite.sensors import extract_wifi_rssi

        data = make_data()
        data.properties = make_properties_message(battery=80)
        assert extract_wifi_rssi(data) is None


class TestGetBladeHeight:
    """Test blade height extraction with fallback."""

    def test_blade_height_from_snapshot(self):
        """Snapshot blade_height preferred when > 0."""
        from custom_components.mammotion_lite.sensors import get_blade_height

        data = make_data()
        data.snapshot = make_snapshot(blade_height=50)
        assert get_blade_height(data) == 50

    def test_blade_height_from_properties_fallback(self):
        """Falls back to properties knifeHeight."""
        from custom_components.mammotion_lite.sensors import get_blade_height

        data = make_data()
        data.properties = make_properties_message(knife_height=45)
        assert get_blade_height(data) == 45

    def test_blade_height_none_when_no_data(self):
        """Returns None when no data."""
        from custom_components.mammotion_lite.sensors import get_blade_height

        data = make_data()
        assert get_blade_height(data) is None
