"""Tests for uncovered branches in device_tracker_helpers."""

from __future__ import annotations

from custom_components.mammotion_lite.device_tracker_helpers import (
    NEAR_ZERO_THRESHOLD,
    extract_coordinates,
)
from tests.conftest import FakePropertyItems, FakePropertyValue, FakePropertiesParams, FakeThingPropertiesMessage, make_data


class TestCoordinateBranches:
    """Cover remaining branches in extract_coordinates."""

    def test_coordinate_value_as_json_string(self):
        """Coordinate value stored as JSON string is parsed correctly."""
        import json

        data = make_data()
        items = FakePropertyItems(coordinate=FakePropertyValue(json.dumps({"lat": -33.0, "lon": 151.0})))
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        result = extract_coordinates(data)
        assert result == (-33.0, 151.0)

    def test_coordinate_value_as_dict(self):
        """Coordinate value stored as dict (pre-parsed) works."""
        data = make_data()
        items = FakePropertyItems(coordinate=FakePropertyValue({"lat": -33.0, "lon": 151.0}))
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        result = extract_coordinates(data)
        assert result == (-33.0, 151.0)

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
        """NEAR_ZERO_THRESHOLD is importable and has the expected value."""
        assert NEAR_ZERO_THRESHOLD == 0.01
