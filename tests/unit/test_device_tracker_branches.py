"""Tests for uncovered branches in device_tracker_helpers."""

from __future__ import annotations

import math

import pytest

from custom_components.mammotion_lite.device_tracker_helpers import (
    NEAR_ZERO_THRESHOLD_RAD,
    extract_coordinates,
)
from tests.conftest import FakePropertyItems, FakePropertyValue, FakePropertiesParams, FakeThingPropertiesMessage, make_data


class TestCoordinateBranches:
    """Cover remaining branches in extract_coordinates."""

    def test_coordinate_value_as_json_string(self):
        """Coordinate value stored as JSON string is parsed and converted."""
        import json

        lat_rad = -33.0 * math.pi / 180
        lon_rad = 151.0 * math.pi / 180
        data = make_data()
        items = FakePropertyItems(
            coordinate=FakePropertyValue(json.dumps({"lat": lat_rad, "lon": lon_rad}))
        )
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        lat, lon = extract_coordinates(data)
        assert lat == pytest.approx(-33.0, abs=0.001)
        assert lon == pytest.approx(151.0, abs=0.001)

    def test_coordinate_value_as_dict(self):
        """Coordinate value stored as dict (pre-parsed) works."""
        lat_rad = -33.0 * math.pi / 180
        lon_rad = 151.0 * math.pi / 180
        data = make_data()
        items = FakePropertyItems(
            coordinate=FakePropertyValue({"lat": lat_rad, "lon": lon_rad})
        )
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        lat, lon = extract_coordinates(data)
        assert lat == pytest.approx(-33.0, abs=0.001)
        assert lon == pytest.approx(151.0, abs=0.001)

    def test_coordinate_missing_lat_key(self):
        """Coordinate dict without lat key returns None."""
        data = make_data()
        items = FakePropertyItems(coordinate=FakePropertyValue({"lon": 151.0}))
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        assert extract_coordinates(data) is None

    def test_coordinate_missing_lon_key(self):
        """Coordinate dict without lon key returns None."""
        data = make_data()
        items = FakePropertyItems(coordinate=FakePropertyValue({"lat": -33.0}))
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        assert extract_coordinates(data) is None

    def test_threshold_constant_is_importable(self):
        """NEAR_ZERO_THRESHOLD_RAD is importable and has the expected value."""
        assert NEAR_ZERO_THRESHOLD_RAD == 0.01
