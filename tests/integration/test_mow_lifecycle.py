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

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pymammotion.proto import RptAct

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
PATCH_COMMAND = "custom_components.mammotion_lite.MammotionCommand"

# Entity IDs
BATTERY = "sensor.luba_vslkjx_battery"
ACTIVITY = "sensor.luba_vslkjx_activity"
PROGRESS = "sensor.luba_vslkjx_job_progress"
LAST_EVENT = "sensor.luba_vslkjx_last_event"
ONLINE = "binary_sensor.luba_vslkjx_online"


def _rpt_acts_sent(entry) -> list[RptAct]:
    """Extract rpt_act values from all request_iot_sys calls on the entry's commands mock."""
    commands = entry.runtime_data.commands
    acts = []
    for call in commands.request_iot_sys.call_args_list:
        rpt_act = call.kwargs.get("rpt_act")
        if rpt_act is not None:
            acts.append(rpt_act)
    return acts


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
        patch(PATCH_COMMAND, return_value=MagicMock()),
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

        # -- Phase 1: Task started event (1301) --
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

        # Verify RPT_START command was sent (not just any send_raw call)
        acts = _rpt_acts_sent(entry)
        assert RptAct.RPT_START in acts, f"Expected RPT_START in {acts}"

        # Last event sensor shows "Task started"
        state = hass.states.get(LAST_EVENT)
        assert state.state == "Task started"
        assert state.attributes["code"] == "1301"

        # -- Phase 2: Snapshot pushes during mowing --
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

        # Second snapshot: 80% battery, 55% progress
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

        # Clear call history so we can check RPT_STOP specifically
        entry.runtime_data.commands.request_iot_sys.reset_mock()

        # -- Phase 3: Docked/charging event (1307) --
        await captured.on_event(make_event_message(code="1307"))
        await hass.async_block_till_done()

        # Verify RPT_STOP command was sent (not just any call)
        acts = _rpt_acts_sent(entry)
        assert RptAct.RPT_STOP in acts, f"Expected RPT_STOP in {acts}"

        # Last event sensor shows "Docked and charging"
        state = hass.states.get(LAST_EVENT)
        assert state.state == "Docked and charging"
        assert state.attributes["code"] == "1307"

    async def test_returning_to_base_keeps_reporting(self, hass: HomeAssistant):
        """Event 1304 (returning) does NOT trigger RPT_STOP - reporting continues."""
        entry, client, captured = await _setup(hass)

        # Start mowing
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.reporting_active is True

        # Clear call history
        data.commands.request_iot_sys.reset_mock()

        # Returning to base event
        await captured.on_event(make_event_message(code="1304"))
        await hass.async_block_till_done()

        # No RPT_STOP should have been sent
        acts = _rpt_acts_sent(entry)
        assert RptAct.RPT_STOP not in acts, f"Unexpected RPT_STOP in {acts}"
        assert data.reporting_active is True

        # Last event updated
        assert hass.states.get(LAST_EVENT).state == "Returning to base"

    async def test_task_completed_keeps_reporting(self, hass: HomeAssistant):
        """Event 1305 (task completed) does NOT trigger RPT_STOP.

        The mower sends 1305 before 1304 (returning). We keep reporting
        until the mower is actually docked (1307).
        """
        entry, client, captured = await _setup(hass)

        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.reporting_active is True

        data.commands.request_iot_sys.reset_mock()

        # Task completed
        await captured.on_event(make_event_message(code="1305"))
        await hass.async_block_till_done()

        acts = _rpt_acts_sent(entry)
        assert RptAct.RPT_STOP not in acts
        assert data.reporting_active is True

        # Only stops when docked
        await captured.on_event(make_event_message(code="1307"))
        await hass.async_block_till_done()

        acts = _rpt_acts_sent(entry)
        assert RptAct.RPT_STOP in acts
        assert data.reporting_active is False

    async def test_mow_complete_on_progress_drop(self, hass: HomeAssistant):
        """Progress dropping from >=90% to 0 records mow completion timestamp."""
        entry, client, captured = await _setup(hass)
        data = entry.runtime_data
        data.area_names = {999: "Front lawn"}

        fake_device = MagicMock()
        fake_device.location.work_zone = 999
        client.get_device_by_name = MagicMock(return_value=fake_device)

        # Mowing at 95% in zone 999
        await captured.on_state_changed(make_snapshot(area=95 << 16, online=True))
        await hass.async_block_till_done()

        # Progress resets to 0 (mow complete)
        await captured.on_state_changed(make_snapshot(area=0, online=True))
        await hass.async_block_till_done()

        assert 999 in data.mow_history
        from datetime import datetime, timezone
        delta = datetime.now(timezone.utc) - data.mow_history[999]
        assert delta.total_seconds() < 5

    async def test_low_progress_drop_does_not_record(self, hass: HomeAssistant):
        """Progress dropping from <90% to 0 does not record (mow was cancelled early)."""
        entry, client, captured = await _setup(hass)
        data = entry.runtime_data
        data.area_names = {999: "Front lawn"}

        fake_device = MagicMock()
        fake_device.location.work_zone = 999
        client.get_device_by_name = MagicMock(return_value=fake_device)

        # Mowing at 30%
        await captured.on_state_changed(make_snapshot(area=30 << 16, online=True))
        await hass.async_block_till_done()

        # Progress resets to 0 (cancelled)
        await captured.on_state_changed(make_snapshot(area=0, online=True))
        await hass.async_block_till_done()

        assert 999 not in data.mow_history

    async def test_mow_complete_records_all_task_zones(self, hass: HomeAssistant):
        """Multi-zone task records timestamps for every zone visited during the mow."""
        entry, client, captured = await _setup(hass)
        data = entry.runtime_data
        data.area_names = {111: "Front lawn", 222: "Side strip", 333: "Nature strip"}

        fake_device = MagicMock()
        fake_device.location.work_zone = 111
        client.get_device_by_name = MagicMock(return_value=fake_device)

        # Mower starts in zone 111
        await captured.on_state_changed(make_snapshot(area=40 << 16, online=True))
        await hass.async_block_till_done()

        # Mid-mow it crosses into zone 333
        fake_device.location.work_zone = 333
        await captured.on_state_changed(make_snapshot(area=95 << 16, online=True))
        await hass.async_block_till_done()

        # Progress resets to 0
        await captured.on_state_changed(make_snapshot(area=0, online=True))
        await hass.async_block_till_done()

        assert 111 in data.mow_history, "Front lawn should be recorded"
        assert 333 in data.mow_history, "Nature strip should be recorded"
        assert 222 not in data.mow_history, "Side strip was not in the task"

    async def test_mow_complete_records_zone_observed_via_work_zone(
        self, hass: HomeAssistant
    ):
        """Records zone tracked via device.location.work_zone during mowing.

        Realistic: pymammotion's `device.work.zone_hashs` is never populated
        with the active task's zones (it's only cleared at progress=0). The
        actual signal is `device.location.work_zone`, which is updated as the
        mower enters each zone. By completion the mower has exited the last
        zone (work_zone=0), so we must accumulate zones during the mow.
        """
        entry, client, captured = await _setup(hass)
        data = entry.runtime_data
        data.area_names = {999: "Front lawn"}

        fake_device = MagicMock()
        fake_device.location.work_zone = 999
        client.get_device_by_name = MagicMock(return_value=fake_device)

        # 95% inside zone 999
        await captured.on_state_changed(make_snapshot(area=95 << 16, online=True))
        await hass.async_block_till_done()

        # Mower exits the zone shortly before completion (work_zone resets to 0)
        fake_device.location.work_zone = 0
        await captured.on_state_changed(make_snapshot(area=100 << 16, online=True))
        await hass.async_block_till_done()

        # Progress drops to 0 -> completion. zone_hashs on the snapshot stays
        # empty (matching real pymammotion behavior).
        await captured.on_state_changed(make_snapshot(area=0, online=True))
        await hass.async_block_till_done()

        assert 999 in data.mow_history, (
            "Front lawn should be recorded - zone was observed during mowing"
        )

    async def test_sensors_show_unknown_before_any_push(self, hass: HomeAssistant):
        """Before any push data, sensor entities render as 'unknown' in HA."""
        entry, client, captured = await _setup(hass)

        assert hass.states.get(BATTERY).state == "unknown"
        assert hass.states.get(ACTIVITY).state == "unknown"
        assert hass.states.get(PROGRESS).state == "unknown"
        assert hass.states.get(LAST_EVENT).state == "unknown"
