"""Integration test: full mow lifecycle simulation.

Simulates the complete mowing lifecycle through the real callback chain:
1. Event 1301 (task started) -> RPT_START command sent, keepalive started
2. Snapshot pushes arrive -> sensors update with battery, activity, progress
3. Event 1307 (docked/charging) -> RPT_STOP command sent, keepalive stopped
4. Sensors show final state

This is the core user-visible flow. If this test passes, the integration
correctly handles a mow session from start to finish.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from custom_components.mammotion_lite.const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
)
from tests.conftest import (
    make_capturing_client,
    make_event_message,
    make_snapshot,
)

PATCH_CLIENT = "custom_components.mammotion_lite.MammotionClient"
PATCH_SESSION = "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession"

# Entity IDs
BATTERY = "sensor.luba_vslkjx_battery"
ACTIVITY = "sensor.luba_vslkjx_activity"
PROGRESS = "sensor.luba_vslkjx_job_progress"
LAST_EVENT = "sensor.luba_vslkjx_last_event"
ONLINE = "binary_sensor.luba_vslkjx_online"


async def _setup(hass: HomeAssistant):
    """Set up integration with capturing client, return (entry, client, captured)."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    client, captured = make_capturing_client()
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

    with (
        patch(PATCH_CLIENT, return_value=client),
        patch(PATCH_SESSION, return_value=MagicMock()),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.LOADED
    return entry, client, captured


class TestMowLifecycle:
    """Simulate a complete mow session through the callback chain."""

    async def test_full_mow_cycle(self, hass: HomeAssistant):
        """Complete mow lifecycle: start -> mowing -> docked."""
        entry, client, captured = await _setup(hass)
        handle = client.mower("Luba-VSLKJX")

        # -- Phase 1: Task started event (1301) --
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

        # Verify RPT_START command was sent
        assert handle.send_raw.await_count >= 1, "RPT_START should have been sent"

        # Last event sensor shows "Task started"
        state = hass.states.get(LAST_EVENT)
        assert state.state == "Task started"
        assert state.attributes["code"] == "1301"

        # -- Phase 2: Snapshot pushes during mowing --
        # First snapshot: 95% battery, mowing, 10% progress
        await captured.on_state_changed(
            make_snapshot(
                battery_level=95,
                mowing_activity="mowing",
                area=10 << 16,
                online=True,
            )
        )
        await hass.async_block_till_done()

        assert hass.states.get(BATTERY).state == "95"
        assert hass.states.get(ACTIVITY).state == "mowing"
        assert hass.states.get(PROGRESS).state == "10"
        assert hass.states.get(ONLINE).state == "on"

        # Second snapshot: 80% battery, mowing, 55% progress
        await captured.on_state_changed(
            make_snapshot(
                battery_level=80,
                mowing_activity="mowing",
                area=55 << 16,
                online=True,
            )
        )
        await hass.async_block_till_done()

        assert hass.states.get(BATTERY).state == "80"
        assert hass.states.get(PROGRESS).state == "55"

        # Record send_raw call count before RPT_STOP
        calls_before_stop = handle.send_raw.await_count

        # -- Phase 3: Docked/charging event (1307) --
        await captured.on_event(make_event_message(code="1307"))
        await hass.async_block_till_done()

        # Verify RPT_STOP command was sent (one more call)
        assert handle.send_raw.await_count > calls_before_stop, "RPT_STOP should have been sent"

        # Last event sensor shows "Docked and charging"
        state = hass.states.get(LAST_EVENT)
        assert state.state == "Docked and charging"
        assert state.attributes["code"] == "1307"

    async def test_returning_to_base_keeps_reporting(self, hass: HomeAssistant):
        """Event 1304 (returning) does NOT trigger RPT_STOP - reporting continues."""
        entry, client, captured = await _setup(hass)
        handle = client.mower("Luba-VSLKJX")

        # Start mowing
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

        # Runtime data should have reporting_active
        data = entry.runtime_data
        assert data.reporting_active is True

        # Returning to base event
        await captured.on_event(make_event_message(code="1304"))
        await hass.async_block_till_done()

        # Reporting should still be active
        assert data.reporting_active is True

        # Last event updated
        assert hass.states.get(LAST_EVENT).state == "Returning to base"

    async def test_task_completed_keeps_reporting(self, hass: HomeAssistant):
        """Event 1305 (task completed) does NOT trigger RPT_STOP.

        The mower sends 1305 before 1304 (returning). We keep reporting
        until the mower is actually docked (1307).
        """
        entry, client, captured = await _setup(hass)

        # Start mowing
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.reporting_active is True

        # Task completed
        await captured.on_event(make_event_message(code="1305"))
        await hass.async_block_till_done()

        # Still reporting
        assert data.reporting_active is True

        # Only stops when docked
        await captured.on_event(make_event_message(code="1307"))
        await hass.async_block_till_done()

        assert data.reporting_active is False

    async def test_sensors_show_unknown_before_any_push(self, hass: HomeAssistant):
        """Before any push data, sensors show unknown (not stale values)."""
        entry, client, captured = await _setup(hass)

        assert hass.states.get(BATTERY).state == "unknown"
        assert hass.states.get(ACTIVITY).state == "unknown"
        assert hass.states.get(PROGRESS).state == "unknown"
        assert hass.states.get(LAST_EVENT).state == "unknown"
