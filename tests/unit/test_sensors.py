"""Tests for mammotion_lite sensor value extraction functions."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from custom_components.mammotion_lite.const import EVENT_CODE_LABELS, EVENT_CODE_TO_ACTIVITY
from tests.conftest import (
    make_data,
    make_properties_message,
    make_snapshot,
)


class TestDispatchSensorUpdate:
    """dispatch_sensor_update records when sensor push data arrived."""

    def test_sensor_dispatch_sets_timestamp(self):
        """dispatch_sensor_update sets last_data_update to current UTC time."""
        data = make_data()
        assert data.last_data_update is None
        data.dispatch_sensor_update()
        assert data.last_data_update is not None
        assert isinstance(data.last_data_update, datetime)

    def test_plain_dispatch_does_not_set_timestamp(self):
        """dispatch_update (events/status) does NOT set last_data_update."""
        data = make_data()
        data.dispatch_update()
        assert data.last_data_update is None


class TestGetBattery:
    """Test battery value extraction with timestamp-based source selection.

    When both snapshot and properties have battery data, the one with the
    latest timestamp wins. This prevents stale snapshot values (e.g. 64%
    from end of mowing) overriding fresh properties pushes (e.g. 78%
    from charging).
    """

    def test_battery_from_newer_snapshot(self):
        """Snapshot battery used when its timestamp is newer than properties."""
        from custom_components.mammotion_lite.sensors import get_battery

        data = make_data()
        # Snapshot at T=2000, properties at T=1000 -> snapshot wins
        data.snapshot = make_snapshot(battery_level=85, timestamp_ms=2000)
        data.properties = make_properties_message(battery=70, battery_time=1000)
        assert get_battery(data) == 85

    def test_battery_from_newer_properties(self):
        """Properties battery used when its timestamp is newer than snapshot.

        This is the key fix: after RPT_STOP, the snapshot is stale (from
        end of mowing) but properties push arrives with fresh charging data.
        """
        from custom_components.mammotion_lite.sensors import get_battery

        data = make_data()
        # Snapshot at T=1000 (stale), properties at T=2000 (fresh) -> properties wins
        data.snapshot = make_snapshot(battery_level=64, timestamp_ms=1000)
        data.properties = make_properties_message(battery=78, battery_time=2000)
        assert get_battery(data) == 78

    def test_battery_from_snapshot_preferred(self):
        """Snapshot battery_level is preferred when > 0 and no properties."""
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
    """Test activity value extraction with fallback chain.

    Priority: event code activity mapping -> snapshot -> event label -> deviceState.
    Event codes are the most timely signal during state transitions - the snapshot
    may be stale from a previous probe until the next state push arrives.
    """

    def test_event_code_takes_priority_over_stale_snapshot(self):
        """Event-derived activity overrides a stale snapshot.

        This is the core bug fix: after 1301 (task started), the snapshot
        still says "ready" from the initial probe. The event code must win.
        """
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.snapshot = make_snapshot(mowing_activity="ready")
        data.last_event_code = "1301"
        assert get_activity(data) == EVENT_CODE_TO_ACTIVITY["1301"]

    def test_manual_start_shows_mowing(self):
        """Event 1201 (manual/app start) shows mowing activity."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.snapshot = make_snapshot(mowing_activity="ready")
        data.last_event_code = "1201"
        assert get_activity(data) == "mowing"

    def test_returning_event_shows_returning(self):
        """Event 1304 (returning to base) shows returning activity."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.last_event_code = "1304"
        assert get_activity(data) == "returning"

    def test_docked_charging_event_shows_charging(self):
        """Event 1307 (docked/charging) shows charging activity."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.last_event_code = "1307"
        assert get_activity(data) == "charging"

    def test_cancelled_event_shows_returning(self):
        """Event 1302 (task cancelled) shows returning - mower heads to base."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.last_event_code = "1302"
        assert get_activity(data) == "returning"

    def test_snapshot_used_when_no_event(self):
        """Snapshot mowing_activity used when no event code is set."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.snapshot = make_snapshot(mowing_activity="mowing")
        assert get_activity(data) == "mowing"

    def test_unknown_zero_snapshot_shows_idle(self):
        """Snapshot mowing_activity='unknown(0)' means the mower is idle.

        pymammotion returns 'unknown(0)' when the mower isn't actively doing
        anything. After restart, the initial probe returns this - the user
        should see 'idle', not 'unknown'.
        """
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.snapshot = make_snapshot(mowing_activity="unknown(0)")
        assert get_activity(data) == "idle"

    def test_activity_fallback_to_device_state(self):
        """Falls back to properties deviceState when no event or snapshot."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.properties = make_properties_message(device_state="standby")
        assert get_activity(data) == "standby"

    def test_activity_none_when_no_data(self):
        """Returns None when no data sources available."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        assert get_activity(data) is None

    def test_event_without_activity_mapping_falls_to_snapshot(self):
        """Unknown event codes without activity mapping fall through to snapshot."""
        from custom_components.mammotion_lite.sensors import get_activity

        data = make_data()
        data.snapshot = make_snapshot(mowing_activity="mowing")
        data.last_event_code = "9999"  # unknown code, no activity mapping
        assert get_activity(data) == "mowing"


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


class TestGetZoneHash:
    """Test mowing zone hash extraction from snapshot."""

    def test_zone_hash_from_snapshot(self):
        """Returns the ub_zone_hash from snapshot work data during mowing."""
        from custom_components.mammotion_lite.sensors import get_zone_hash

        data = make_data()
        data.snapshot = make_snapshot(ub_zone_hash=123456789)
        assert get_zone_hash(data) == 123456789

    def test_zone_hash_none_when_zero(self):
        """Returns None when zone hash is 0 (no active zone)."""
        from custom_components.mammotion_lite.sensors import get_zone_hash

        data = make_data()
        data.snapshot = make_snapshot(ub_zone_hash=0)
        assert get_zone_hash(data) is None

    def test_zone_name_from_area_names(self):
        """Returns human-readable zone name when area_name mapping exists."""
        from custom_components.mammotion_lite.sensors import get_zone_name

        data = make_data()
        data.snapshot = make_snapshot(ub_zone_hash=123456789)
        data.area_names = {123456789: "Backyard upper"}
        assert get_zone_name(data) == "Backyard upper"

    def test_zone_name_falls_back_to_hash(self):
        """Returns hash as string when no name mapping exists."""
        from custom_components.mammotion_lite.sensors import get_zone_name

        data = make_data()
        data.snapshot = make_snapshot(ub_zone_hash=987654321)
        data.area_names = {}
        assert get_zone_name(data) == "987654321"

    def test_zone_name_none_when_no_zone(self):
        """Returns None when no active zone."""
        from custom_components.mammotion_lite.sensors import get_zone_name

        data = make_data()
        data.area_names = {123: "Front yard"}
        assert get_zone_name(data) is None

    def test_zone_hash_none_when_no_snapshot(self):
        """Returns None when no snapshot available."""
        from custom_components.mammotion_lite.sensors import get_zone_hash

        data = make_data()
        assert get_zone_hash(data) is None


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
    """Test WiFi RSSI extraction from snapshot (preferred) and properties (fallback)."""

    def test_rssi_from_snapshot_preferred(self):
        """Snapshot report_data.connect.wifi_rssi is used when available.

        This is the preferred path - available from RPT reports during mowing
        and the initial probe. If removed, the sensor would only update every
        30 minutes from properties push.
        """
        from custom_components.mammotion_lite.sensors import extract_wifi_rssi

        data = make_data()
        data.snapshot = make_snapshot(wifi_rssi=-67)
        assert extract_wifi_rssi(data) == -67

    def test_rssi_from_snapshot_overrides_properties(self):
        """Snapshot RSSI takes priority over properties push RSSI."""
        from custom_components.mammotion_lite.sensors import extract_wifi_rssi

        data = make_data()
        data.snapshot = make_snapshot(wifi_rssi=-67)
        data.properties = make_properties_message(network_info={"wifi_rssi": -55})
        assert extract_wifi_rssi(data) == -67

    def test_rssi_from_snapshot_zero_falls_through(self):
        """Snapshot RSSI of 0 (uninitialised) falls through to properties."""
        from custom_components.mammotion_lite.sensors import extract_wifi_rssi

        data = make_data()
        data.snapshot = make_snapshot(wifi_rssi=0)
        data.properties = make_properties_message(network_info={"wifi_rssi": -55})
        assert extract_wifi_rssi(data) == -55

    def test_rssi_from_json_string(self):
        """Extracts wifi_rssi from JSON string networkInfo (properties fallback)."""
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
