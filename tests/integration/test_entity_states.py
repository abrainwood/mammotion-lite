"""Integration tests: verify HA entity states update from push data.

These tests set up the full integration with real platforms (sensor,
binary_sensor, device_tracker, camera) and simulate MQTT push data
by invoking the captured callback handlers. They verify the actual
HA entity states - not just extraction functions.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.mammotion_lite.const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
)

# Entity IDs are derived from unique_id slugification, not from DOMAIN prefix.
# unique_id = "mammotion_lite_Luba-VSLKJX_battery" -> entity_id = "sensor.luba_vslkjx_battery"
BATTERY = "sensor.luba_vslkjx_battery"
ACTIVITY = "sensor.luba_vslkjx_activity"
PROGRESS = "sensor.luba_vslkjx_job_progress"
LAST_EVENT = "sensor.luba_vslkjx_last_event"
WIFI = "sensor.luba_vslkjx_wifi_signal"
BLADE = "sensor.luba_vslkjx_blade_height"
ONLINE = "binary_sensor.luba_vslkjx_online"
TRACKER = "device_tracker.luba_vslkjx_location"
from tests.conftest import (
    CapturedCallbacks,
    FakeStatusParams,
    FakeStatusType,
    FakeStatusValue,
    FakeThingStatusMessage,
    make_capturing_client,
    make_event_message,
    make_properties_message,
    make_snapshot,
)

PATCH_CLIENT = "custom_components.mammotion_lite.MammotionClient"
PATCH_SESSION = "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession"


def _make_entry(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCOUNTNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_DEVICE_NAME: "Luba-VSLKJX",
            CONF_DEVICE_IOT_ID: "abc123",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_with_platforms(
    hass: HomeAssistant, client: MagicMock
) -> None:
    """Set up the integration with real platforms (no PLATFORMS patch)."""
    entry = _make_entry(hass)
    with (
        patch(PATCH_CLIENT, return_value=client),
        patch(PATCH_SESSION, return_value=MagicMock()),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert entry.state == ConfigEntryState.LOADED
    return entry


class TestSensorEntitiesFromPropertiesPush:
    """Test that sensor entities show correct state after a properties push."""

    async def test_battery_sensor_shows_value_from_properties(self, hass: HomeAssistant):
        """Battery sensor reports the value from a properties push."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        # Simulate properties push with battery=72
        props = make_properties_message(battery=72, knife_height=45)
        await captured.on_properties(props)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.luba_vslkjx_battery")
        assert state is not None, "Battery sensor entity not found"
        assert state.state == "72"

    async def test_blade_height_sensor_from_properties(self, hass: HomeAssistant):
        """Blade height sensor reports value from properties push."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        props = make_properties_message(knife_height=55)
        await captured.on_properties(props)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.luba_vslkjx_blade_height")
        assert state is not None, "Blade height sensor entity not found"
        assert state.state == "55"

    async def test_wifi_signal_sensor_from_properties(self, hass: HomeAssistant):
        """WiFi signal sensor reports RSSI from properties push."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        props = make_properties_message(network_info={"wifi_rssi": -62})
        await captured.on_properties(props)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.luba_vslkjx_wifi_signal")
        assert state is not None, "WiFi signal sensor entity not found"
        assert state.state == "-62"


class TestSensorEntitiesFromSnapshotPush:
    """Test that sensor entities show correct state after a snapshot push."""

    async def test_battery_from_snapshot_overrides_properties(self, hass: HomeAssistant):
        """Snapshot battery takes priority over properties battery."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        # First push properties with battery=60
        await captured.on_properties(make_properties_message(battery=60))
        await hass.async_block_till_done()

        # Then push snapshot with battery=85 (should override)
        await captured.on_state_changed(make_snapshot(battery_level=85))
        await hass.async_block_till_done()

        state = hass.states.get("sensor.luba_vslkjx_battery")
        assert state.state == "85"

    async def test_activity_from_snapshot(self, hass: HomeAssistant):
        """Activity sensor shows mowing_activity from snapshot."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        await captured.on_state_changed(make_snapshot(mowing_activity="mowing"))
        await hass.async_block_till_done()

        state = hass.states.get("sensor.luba_vslkjx_activity")
        assert state is not None
        assert state.state == "mowing"

    async def test_job_progress_from_snapshot(self, hass: HomeAssistant):
        """Job progress sensor shows percentage from area >> 16."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        # 67% encoded in upper 16 bits
        await captured.on_state_changed(make_snapshot(area=67 << 16))
        await hass.async_block_till_done()

        state = hass.states.get("sensor.luba_vslkjx_job_progress")
        assert state is not None
        assert state.state == "67"


class TestBinarySensorFromStatusPush:
    """Test that the online binary sensor updates from status pushes."""

    async def test_online_after_connected_status(self, hass: HomeAssistant):
        """Binary sensor is on after connected status push."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        connected = FakeThingStatusMessage(
            params=FakeStatusParams(
                status=FakeStatusValue(value=FakeStatusType.CONNECTED)
            )
        )
        await captured.on_status(connected)
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.luba_vslkjx_online")
        assert state is not None, "Online binary sensor not found"
        assert state.state == "on"

    async def test_offline_after_disconnected_status(self, hass: HomeAssistant):
        """Binary sensor is off after disconnected status push."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        disconnected = FakeThingStatusMessage(
            params=FakeStatusParams(
                status=FakeStatusValue(value=FakeStatusType.DISCONNECTED)
            )
        )
        await captured.on_status(disconnected)
        await hass.async_block_till_done()

        state = hass.states.get("binary_sensor.luba_vslkjx_online")
        assert state is not None
        assert state.state == "off"


class TestDeviceTrackerFromPropertiesPush:
    """Test that device tracker updates from coordinate properties push."""

    async def test_location_from_coordinate_push(self, hass: HomeAssistant):
        """Device tracker reports lat/lon from coordinate property."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        props = make_properties_message(
            coordinate={"lat": -33.8688, "lon": 151.2093}
        )
        await captured.on_properties(props)
        await hass.async_block_till_done()

        state = hass.states.get("device_tracker.luba_vslkjx_location")
        assert state is not None, "Device tracker entity not found"
        assert state.attributes.get("latitude") == pytest.approx(-33.8688)
        assert state.attributes.get("longitude") == pytest.approx(151.2093)


class TestLastEventSensorFromEventPush:
    """Test that last_event sensor updates from event pushes."""

    async def test_last_event_shows_label_and_attrs(self, hass: HomeAssistant):
        """Last event sensor shows label with code and timestamp in attrs."""
        client, captured = make_capturing_client()
        await _setup_with_platforms(hass, client)

        event = make_event_message(code="1301")
        await captured.on_event(event)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.luba_vslkjx_last_event")
        assert state is not None, "Last event sensor not found"
        assert state.state == "Task started"
        assert state.attributes.get("code") == "1301"
        assert "timestamp" in state.attributes
