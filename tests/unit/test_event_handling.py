"""Tests for event handling and RPT trigger logic in mammotion_lite."""

from __future__ import annotations

import json

import pytest

from custom_components.mammotion_lite.const import (
    EVENT_CODE_LABELS,
    START_REPORTING_CODES,
    STOP_REPORTING_CODES,
)
from custom_components.mammotion_lite.event_handling import extract_event_code, get_event_label
from tests.conftest import (
    FakeEventParams,
    FakeEventValue,
    FakeThingEventMessage,
    make_event_message,
)


class TestEventCodeExtraction:
    """Test extraction of notification codes from ThingEventMessage."""

    def test_extract_code_from_device_notification_event(self):
        """Code is extracted from device_notification_event JSON payload."""
        event = make_event_message(code="1301")
        assert extract_event_code(event) == "1301"

    def test_extract_code_returns_none_for_non_notification_event(self):
        """Non-notification events return None."""
        event = make_event_message(identifier="device_protobuf_msg_event")
        assert extract_event_code(event) is None

    def test_extract_code_returns_none_when_no_value(self):
        """Event with no value returns None."""
        event = FakeThingEventMessage(
            params=FakeEventParams(identifier="device_notification_event", value=None)
        )
        assert extract_event_code(event) is None

    def test_extract_code_returns_none_for_malformed_json(self):
        """Malformed JSON in event data returns None."""
        event = FakeThingEventMessage(
            params=FakeEventParams(
                identifier="device_notification_event",
                value=FakeEventValue(data="not valid json"),
            )
        )
        assert extract_event_code(event) is None

    def test_extract_code_returns_none_for_missing_code_field(self):
        """JSON without a 'code' field returns None."""
        event = FakeThingEventMessage(
            params=FakeEventParams(
                identifier="device_notification_event",
                value=FakeEventValue(data=json.dumps({"other": "data"})),
            )
        )
        assert extract_event_code(event) is None

    def test_extract_code_handles_dict_value_data(self):
        """Code extraction works when value.data is already a dict."""
        event = FakeThingEventMessage(
            params=FakeEventParams(
                identifier="device_notification_event",
                value=FakeEventValue(data={"code": "1305"}),
            )
        )
        assert extract_event_code(event) == "1305"

    def test_extract_code_converts_int_code_to_string(self):
        """Integer codes are converted to strings."""
        event = FakeThingEventMessage(
            params=FakeEventParams(
                identifier="device_notification_event",
                value=FakeEventValue(data=json.dumps({"code": 1307})),
            )
        )
        assert extract_event_code(event) == "1307"


class TestEventCodeLabels:
    """Test event code to label mapping."""

    def test_known_code_returns_label(self):
        """Known event codes return their human-readable labels."""
        assert EVENT_CODE_LABELS["1301"] == "Task started"
        assert EVENT_CODE_LABELS["1307"] == "Docked and charging"

    def test_unknown_code_label_fallback(self):
        """get_event_label returns a fallback for unknown codes."""
        label = get_event_label("9999")
        assert "9999" in label
        assert "unknown" in label.lower() or "Unknown" in label


class TestRptTriggerLogic:
    """Test which event codes trigger RPT_START/STOP."""

    def test_task_started_triggers_rpt_start(self):
        """Event code 1301 (task started) should trigger reporting."""
        assert "1301" in START_REPORTING_CODES

    def test_docked_charging_triggers_rpt_stop(self):
        """Event code 1307 (docked/charging) should stop reporting."""
        assert "1307" in STOP_REPORTING_CODES

    def test_task_completed_does_not_trigger_rpt_stop(self):
        """Event code 1305 (task completed) does NOT trigger RPT_STOP.

        The mower sends 1305 before 1304 (returning) and then 1307 (docked).
        We want to keep reporting until the mower is actually docked.
        """
        assert "1305" not in STOP_REPORTING_CODES

    def test_returning_to_base_does_not_trigger_rpt_stop(self):
        """Event code 1304 (returning) does NOT trigger RPT_STOP."""
        assert "1304" not in STOP_REPORTING_CODES

    def test_task_cancelled_does_not_trigger_rpt_start(self):
        """Event code 1302 (cancelled) does NOT trigger RPT_START."""
        assert "1302" not in START_REPORTING_CODES
