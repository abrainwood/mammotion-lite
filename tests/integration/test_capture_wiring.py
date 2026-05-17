"""Integration test: capture recorder is wired into the on_event callback.

When MAMMOTION_LITE_CAPTURE_DIR is set, the integration's on_event callback
must hand the inbound message to a CaptureRecorder so a JSONL trace is
written for every event.

Proves wiring (callback -> recorder -> file), not serialisation completeness.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

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
    make_properties_message,
    make_snapshot,
    make_status_message,
)

PATCH_CLIENT = "custom_components.mammotion_lite.MammotionClient"
PATCH_SESSION = "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession"
PATCH_COMMAND = "custom_components.mammotion_lite.MammotionCommand"


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


async def test_event_callback_recorded_to_capture_file(
    hass: HomeAssistant, tmp_path, monkeypatch
):
    """on_event callback writes a JSONL line via CaptureRecorder when capture dir is set.

    Proves the recorder is wired into the integration's event handler. Narrow
    assertions: a file appears, has one JSONL line of kind="event", and the
    raw text references the event code so we know payload made it through.
    """
    monkeypatch.setenv("MAMMOTION_LITE_CAPTURE_DIR", str(tmp_path))

    entry, client, captured = await _setup(hass)

    await captured.on_event(make_event_message(code="1301"))
    await hass.async_block_till_done()

    files = [p for p in tmp_path.iterdir() if p.is_file()]
    assert len(files) == 1, f"expected one capture file, got {files}"

    capture_file = files[0]
    raw_lines = capture_file.read_text().splitlines()
    assert len(raw_lines) >= 1

    entry_line = json.loads(raw_lines[0])
    assert entry_line["kind"] == "event"

    # Sanity: the recorded payload references the event code we pushed.
    assert "1301" in capture_file.read_text(), (
        f"capture file should reference event code 1301; contents: "
        f"{capture_file.read_text()!r}"
    )


async def test_capture_failure_does_not_break_event_handling(
    hass: HomeAssistant, tmp_path, monkeypatch, caplog
):
    """A failing recorder.record() must not break event processing.

    Capture is best-effort instrumentation. If the JSONL write fails (disk
    full, permissions, anything), the integration must:
      (a) swallow the exception so the callback completes normally,
      (b) continue processing the event so sensors still update,
      (c) log at WARNING so the user can diagnose why captures aren't appearing.
    """
    monkeypatch.setenv("MAMMOTION_LITE_CAPTURE_DIR", str(tmp_path))

    entry, client, captured = await _setup(hass)

    # Force every record() call on this entry's recorder to blow up.
    recorder = entry.runtime_data.recorder
    monkeypatch.setattr(
        recorder, "record", MagicMock(side_effect=RuntimeError("disk full"))
    )

    last_event_entity = "sensor.luba_vslkjx_last_event"

    with caplog.at_level(logging.WARNING, logger="custom_components.mammotion_lite"):
        # Must not raise.
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

    # Sensor still updated despite capture failure.
    state = hass.states.get(last_event_entity)
    assert state is not None
    assert state.state == "Task started", (
        f"event handling broken by capture failure; last_event state={state.state!r}"
    )

    # WARNING was logged with enough context to diagnose.
    warning_records = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING
        and "custom_components.mammotion_lite" in r.name
    ]
    assert warning_records, (
        f"expected a WARNING about capture failure; got records: "
        f"{[(r.name, r.levelname, r.message) for r in caplog.records]}"
    )
    combined = " ".join(r.getMessage() for r in warning_records).lower()
    assert "record" in combined or "capture" in combined, (
        f"WARNING should mention the operation; got: {combined!r}"
    )
    assert "runtimeerror" in combined or "disk full" in combined, (
        f"WARNING should mention the exception class/message; got: {combined!r}"
    )


async def test_all_callbacks_recorded(
    hass: HomeAssistant, tmp_path, monkeypatch
):
    """All four MQTT callbacks (event, status, properties, state_changed)
    must record into the capture file.

    Slice 6 wired only `on_event`. This test drives wiring for the other
    three callbacks so a real-mow capture is complete (not just events).

    The fakes provide their own .to_dict() (see conftest), matching the
    JSON-clean output that real pymammotion mashumaro classes emit.
    """
    monkeypatch.setenv("MAMMOTION_LITE_CAPTURE_DIR", str(tmp_path))

    entry, client, captured = await _setup(hass)

    # Fire one of each callback type back-to-back.
    await captured.on_event(make_event_message(code="1301"))
    await captured.on_status(make_status_message(connected=True))
    await captured.on_properties(make_properties_message(battery=80))
    await captured.on_state_changed(make_snapshot(battery_level=80, online=True))
    await hass.async_block_till_done()

    files = [p for p in tmp_path.iterdir() if p.is_file()]
    assert len(files) == 1, f"expected exactly one capture file, got {files}"

    capture_file = files[0]
    raw_lines = capture_file.read_text().splitlines()
    assert len(raw_lines) == 4, (
        f"expected 4 JSONL lines (one per callback), got {len(raw_lines)}: "
        f"{raw_lines}"
    )

    kinds = [json.loads(line)["kind"] for line in raw_lines]
    assert set(kinds) == {"event", "status", "property", "state_changed"}, (
        f"expected one of each callback kind, got {kinds}"
    )
