"""Tests for uncovered branches in WiFi RSSI extraction."""

from __future__ import annotations

from custom_components.mammotion_lite.sensors import extract_wifi_rssi
from tests.conftest import FakePropertyItems, FakePropertyValue, FakePropertiesParams, FakeThingPropertiesMessage, make_data


class TestWifiRssiBranches:
    """Cover dict-typed networkInfo branch."""

    def test_rssi_from_dict_value(self):
        """networkInfo stored as dict (pre-parsed) returns RSSI."""
        data = make_data()
        items = FakePropertyItems(networkInfo=FakePropertyValue({"wifi_rssi": -72}))
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        assert extract_wifi_rssi(data) == -72

    def test_rssi_none_for_malformed_json(self):
        """Malformed JSON networkInfo returns None."""
        data = make_data()
        items = FakePropertyItems(networkInfo=FakePropertyValue("not json"))
        data.properties = FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))
        assert extract_wifi_rssi(data) is None
