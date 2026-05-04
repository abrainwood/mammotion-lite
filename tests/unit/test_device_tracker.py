"""Tests for mammotion_lite device tracker coordinate extraction."""

from __future__ import annotations

import logging
import math

import pytest

from custom_components.mammotion_lite.device_tracker_helpers import extract_coordinates
from tests.conftest import make_data, make_properties_message, make_snapshot


class TestExtractCoordinates:
    """Test GPS coordinate extraction.

    Two sources: snapshot.raw.location.device (preferred, degrees from RPT reports)
    and properties coordinate push (fallback, radians from 30-min passive push).
    """

    def test_snapshot_coordinates_preferred(self):
        """Snapshot location.device coordinates are used first (already in degrees)."""
        data = make_data()
        data.snapshot = make_snapshot(latitude=-33.87, longitude=151.21, position_type=4)
        lat, lon = extract_coordinates(data)
        assert lat == pytest.approx(-33.87, abs=0.001)
        assert lon == pytest.approx(151.21, abs=0.001)

    def test_snapshot_rejected_when_position_type_zero(self):
        """Snapshot coordinates with position_type=0 (uninitialised) are rejected.

        Uses valid-looking degree coordinates that would pass the plausibility check.
        Only the position_type=0 guard catches these - if that check is removed,
        this test MUST fail.
        """
        data = make_data()
        data.snapshot = make_snapshot(latitude=-33.87, longitude=151.21, position_type=0)
        result = extract_coordinates(data)
        assert result is None

    def test_snapshot_rejected_when_radian_scale_values(self):
        """Small degree values (likely unconverted radians) are rejected."""
        data = make_data()
        data.snapshot = make_snapshot(latitude=-0.586, longitude=2.630, position_type=4)
        # lat=-0.586 degrees is near the equator - this is a radian value treated as degrees
        # abs(-0.586) < 1.0 so it should be filtered
        result = extract_coordinates(data)
        assert result is None

    def test_radian_coordinates_converted_to_degrees(self):
        """Coordinate values in radians are converted to degrees.

        The mower sends RTK coordinates in radians. For Sydney:
        -0.5909 rad = ~-33.87 deg (latitude)
         2.6384 rad = ~151.21 deg (longitude)
        """
        data = make_data()
        # Sydney in radians
        lat_rad = -33.8688 * math.pi / 180  # -0.59098...
        lon_rad = 151.2093 * math.pi / 180  # 2.63844...
        data.properties = make_properties_message(
            coordinate={"lat": lat_rad, "lon": lon_rad}
        )
        lat, lon = extract_coordinates(data)
        assert lat == pytest.approx(-33.8688, abs=0.001)
        assert lon == pytest.approx(151.2093, abs=0.001)

    def test_near_zero_radians_filtered(self):
        """Coordinates near zero radians (uninitialised GPS) are filtered out."""
        data = make_data()
        data.properties = make_properties_message(
            coordinate={"lat": 0.001, "lon": 0.002}
        )
        result = extract_coordinates(data)
        assert result is None

    def test_exactly_zero_coordinates_filtered(self):
        """Exactly zero coordinates are filtered out."""
        data = make_data()
        data.properties = make_properties_message(
            coordinate={"lat": 0.0, "lon": 0.0}
        )
        result = extract_coordinates(data)
        assert result is None

    def test_no_properties_returns_none(self):
        """Returns None when no properties available."""
        data = make_data()
        result = extract_coordinates(data)
        assert result is None

    def test_no_coordinate_field_returns_none(self):
        """Returns None when properties have no coordinate field."""
        data = make_data()
        data.properties = make_properties_message(battery=80)
        result = extract_coordinates(data)
        assert result is None

    def test_negative_radian_coordinates_pass_threshold(self):
        """Negative radian coordinates with abs > threshold are valid."""
        data = make_data()
        # Melbourne: -37.8136, 144.9631 in radians
        lat_rad = -37.8136 * math.pi / 180
        lon_rad = 144.9631 * math.pi / 180
        data.properties = make_properties_message(
            coordinate={"lat": lat_rad, "lon": lon_rad}
        )
        lat, lon = extract_coordinates(data)
        assert lat == pytest.approx(-37.8136, abs=0.001)
        assert lon == pytest.approx(144.9631, abs=0.001)

    def test_only_both_near_zero_is_filtered(self):
        """Filtering only triggers when both lat and lon are near zero."""
        data = make_data()
        # lat is near zero but lon is not
        lon_rad = 151.0 * math.pi / 180
        data.properties = make_properties_message(
            coordinate={"lat": 0.005, "lon": lon_rad}
        )
        lat, lon = extract_coordinates(data)
        # lat near zero converts to ~0.286 degrees, lon converts to ~151
        assert lat == pytest.approx(0.005 * 180 / math.pi, abs=0.001)
        assert lon == pytest.approx(151.0, abs=0.001)

    def test_real_mower_coordinates_from_live_data(self):
        """Actual values observed from live mower converted correctly.

        Live data showed lat=-0.586106868, lon=2.630138383 (radians)
        which should convert to approximately Sydney coordinates.
        """
        data = make_data()
        data.properties = make_properties_message(
            coordinate={"lat": -0.586106868, "lon": 2.630138383}
        )
        lat, lon = extract_coordinates(data)
        # Should be somewhere in Sydney area
        assert -34.5 < lat < -33.0
        assert 150.0 < lon < 152.0


class TestCoordinateHysteresis:
    """Small coordinate changes should not update the tracker position."""

    def test_small_position_change_ignored(self):
        """Position change under threshold does not update cached coordinates."""
        from custom_components.mammotion_lite.device_tracker import MammotionDeviceTracker

        data = make_data()
        tracker = MammotionDeviceTracker(data, "test_entry")

        # First position: RTK base
        data.snapshot = make_snapshot(latitude=-33.5817, longitude=150.6957, position_type=5)
        tracker._update_coordinates()
        assert tracker._latitude == pytest.approx(-33.5817, abs=0.001)

        # Second position: ~250m east (properties push) - should be ignored
        data.snapshot = None
        data.properties = make_properties_message(
            coordinate={"lat": -33.5814 * math.pi / 180, "lon": 150.6982 * math.pi / 180}
        )
        tracker._update_coordinates()
        # Should still be the original position
        assert tracker._longitude == pytest.approx(150.6957, abs=0.001)

    def test_large_position_change_accepted(self):
        """Position change over threshold updates cached coordinates."""
        from custom_components.mammotion_lite.device_tracker import MammotionDeviceTracker

        data = make_data()
        tracker = MammotionDeviceTracker(data, "test_entry")

        # First position
        data.snapshot = make_snapshot(latitude=-33.5817, longitude=150.6957, position_type=5)
        tracker._update_coordinates()

        # Second position: 1km away - should update
        data.snapshot = make_snapshot(latitude=-33.590, longitude=150.700, position_type=5)
        tracker._update_coordinates()
        assert tracker._latitude == pytest.approx(-33.590, abs=0.001)


class TestRTKBaseFallback:
    """When device coords are garbage but RTK base has valid radians, use RTK base."""

    def test_rtk_base_used_when_device_coords_implausible(self):
        """RTK base radians converted to degrees when device coords are near-zero."""
        data = make_data()
        # Device coords near-zero (converter uninitialised), but RTK base has valid radians
        snapshot = make_snapshot(latitude=-0.00005, longitude=0.000171, position_type=5)
        # Sydney RTK base in radians
        snapshot.raw.location.RTK.latitude = -0.5911
        snapshot.raw.location.RTK.longitude = 2.6384
        data.snapshot = snapshot
        result = extract_coordinates(data)
        assert result is not None
        lat, lon = result
        assert lat == pytest.approx(-33.87, abs=0.2)
        assert lon == pytest.approx(151.2, abs=0.2)

    def test_rtk_base_zero_does_not_fallback(self):
        """When both device coords and RTK base are zero, returns None."""
        data = make_data()
        snapshot = make_snapshot(latitude=-0.00005, longitude=0.000171, position_type=5)
        snapshot.raw.location.RTK.latitude = 0.0
        snapshot.raw.location.RTK.longitude = 0.0
        data.snapshot = snapshot
        assert extract_coordinates(data) is None


class TestCoordinateLogDeduplication:
    """Repeated invalid coordinates should not spam the log."""

    def test_repeated_implausible_coords_log_once(self, caplog):
        """Same implausible coordinates logged only on first call."""
        import custom_components.mammotion_lite.device_tracker_helpers as dth
        dth._last_snapshot_rejection = None  # reset state

        data = make_data()
        data.snapshot = make_snapshot(latitude=-0.00005, longitude=0.000171, position_type=5)

        with caplog.at_level(logging.DEBUG, logger="custom_components.mammotion_lite.device_tracker_helpers"):
            extract_coordinates(data)
            first_count = len(caplog.records)

            caplog.clear()
            extract_coordinates(data)
            second_count = len(caplog.records)

        assert first_count > 0, "First call should produce log output"
        assert second_count == 0, "Repeated call with same coords should not log"

    def test_changed_coords_log_again(self, caplog):
        """When coordinates change, rejection is logged again."""
        import custom_components.mammotion_lite.device_tracker_helpers as dth
        dth._last_snapshot_rejection = None  # reset state

        data = make_data()
        data.snapshot = make_snapshot(latitude=-0.00005, longitude=0.000171, position_type=5)

        with caplog.at_level(logging.DEBUG, logger="custom_components.mammotion_lite.device_tracker_helpers"):
            extract_coordinates(data)
            caplog.clear()

            # Change coordinates
            data.snapshot = make_snapshot(latitude=-0.001, longitude=0.002, position_type=5)
            extract_coordinates(data)

        assert len(caplog.records) > 0, "Changed coords should produce new log output"

    def test_valid_coords_clear_rejection_state(self, caplog):
        """After valid coordinates, a subsequent rejection logs again."""
        import custom_components.mammotion_lite.device_tracker_helpers as dth
        dth._last_snapshot_rejection = None

        data = make_data()

        with caplog.at_level(logging.DEBUG, logger="custom_components.mammotion_lite.device_tracker_helpers"):
            # First: implausible coords (rejected, logged)
            data.snapshot = make_snapshot(latitude=-0.00005, longitude=0.000171, position_type=5)
            extract_coordinates(data)
            caplog.clear()

            # Second: valid coords (accepted, clears rejection state)
            data.snapshot = make_snapshot(latitude=-33.87, longitude=151.21, position_type=5)
            extract_coordinates(data)
            caplog.clear()

            # Third: same implausible coords as first (should log again)
            data.snapshot = make_snapshot(latitude=-0.00005, longitude=0.000171, position_type=5)
            extract_coordinates(data)

        assert len(caplog.records) > 0, "Rejection after valid coords should log again"
