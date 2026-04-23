"""Tests for mammotion_lite constants and helpers."""

from __future__ import annotations

from custom_components.mammotion_lite.const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
    EVENT_CODE_LABELS,
    EVENT_DOCKED_CHARGING,
    EVENT_DOCKED_CHARGING_ALT,
    EVENT_STARTED_ALT,
    EVENT_RETURNING_TO_BASE,
    EVENT_TASK_CANCELLED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_STARTED,
    START_REPORTING_CODES,
    STOP_REPORTING_CODES,
    device_info,
)


def test_domain_is_mammotion_lite():
    """Domain constant matches the integration name."""
    assert DOMAIN == "mammotion_lite"


def test_event_code_constants_exist():
    """All known event code constants match firmware wire values.

    These are protocol-level values from the Mammotion mower firmware,
    discovered via APK decompilation and live MQTT observation.
    DO NOT change without verifying against actual device behavior.
    """
    assert EVENT_TASK_STARTED == "1301"
    assert EVENT_TASK_CANCELLED == "1302"
    assert EVENT_RETURNING_TO_BASE == "1304"
    assert EVENT_TASK_COMPLETED == "1305"
    assert EVENT_DOCKED_CHARGING == "1307"


def test_event_code_labels_maps_all_known_codes():
    """EVENT_CODE_LABELS has entries for all known event codes."""
    for code in [
        EVENT_TASK_STARTED,
        EVENT_TASK_CANCELLED,
        EVENT_RETURNING_TO_BASE,
        EVENT_TASK_COMPLETED,
        EVENT_DOCKED_CHARGING,
    ]:
        assert code in EVENT_CODE_LABELS
        assert isinstance(EVENT_CODE_LABELS[code], str)
        assert len(EVENT_CODE_LABELS[code]) > 0


def test_start_reporting_codes():
    """START_REPORTING_CODES contains scheduled and manual start codes."""
    assert EVENT_TASK_STARTED in START_REPORTING_CODES
    assert EVENT_STARTED_ALT in START_REPORTING_CODES
    assert len(START_REPORTING_CODES) == 2


def test_stop_reporting_codes():
    """STOP_REPORTING_CODES contains scheduled and manual docked/charging codes."""
    assert EVENT_DOCKED_CHARGING in STOP_REPORTING_CODES
    assert EVENT_DOCKED_CHARGING_ALT in STOP_REPORTING_CODES
    assert len(STOP_REPORTING_CODES) == 2


def test_device_info_returns_correct_shape():
    """device_info produces a DeviceInfo with expected identifiers and name."""
    info = device_info("entry123", "Luba-VSLKJX")

    assert info["identifiers"] == {(DOMAIN, "entry123_Luba-VSLKJX")}
    assert info["name"] == "Luba-VSLKJX"
    assert info["manufacturer"] == "Mammotion"


def test_config_key_constants_exist():
    """Config key constants are defined and distinct."""
    keys = {CONF_ACCOUNTNAME, CONF_DEVICE_NAME, CONF_DEVICE_IOT_ID}
    assert len(keys) == 3  # all distinct
