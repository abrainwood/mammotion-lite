"""Tests for mammotion_lite device tracker coordinate extraction."""

from __future__ import annotations

import json

from custom_components.mammotion_lite.device_tracker_helpers import extract_coordinates
from tests.conftest import make_data, make_properties_message


class TestExtractCoordinates:
    """Test GPS coordinate extraction from properties push."""

    def test_valid_coordinates_extracted(self):
        """Valid lat/lon from coordinate property are returned."""
        data = make_data()
        data.properties = make_properties_message(
            coordinate={"lat": -33.8688, "lon": 151.2093}
        )
        lat, lon = extract_coordinates(data)
        assert lat == -33.8688
        assert lon == 151.2093

    def test_near_zero_coordinates_filtered(self):
        """Coordinates near zero (invalid) are filtered out."""
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

    def test_negative_coordinates_pass_threshold(self):
        """Negative coordinates with abs > 0.01 are valid."""
        data = make_data()
        data.properties = make_properties_message(
            coordinate={"lat": -33.0, "lon": -151.0}
        )
        lat, lon = extract_coordinates(data)
        assert lat == -33.0
        assert lon == -151.0

    def test_only_both_near_zero_is_filtered(self):
        """Filtering only triggers when both lat and lon are near zero."""
        data = make_data()
        data.properties = make_properties_message(
            coordinate={"lat": 0.005, "lon": 151.0}
        )
        lat, lon = extract_coordinates(data)
        assert lat == 0.005
        assert lon == 151.0
