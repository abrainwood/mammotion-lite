"""Tests for mammotion_lite device tracker coordinate extraction."""

from __future__ import annotations

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
