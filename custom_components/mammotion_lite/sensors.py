"""Sensor value extraction functions for Mammotion Lite.

Pure functions that extract sensor values from MammotionLiteData.
Separated from the HA entity layer for testability.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .const import EVENT_CODE_TO_ACTIVITY
from .runtime_data import MammotionLiteData

from datetime import datetime

_LOGGER = logging.getLogger(__name__)


def get_last_event_time(data: MammotionLiteData) -> datetime | None:
    """Get the timestamp of the most recent notification event."""
    return data.last_event_time


def get_last_data_update(data: MammotionLiteData) -> datetime | None:
    """Get the timestamp of the most recent push data arrival."""
    return data.last_data_update


def get_battery(data: MammotionLiteData) -> int | None:
    """Get battery from snapshot (preferred) or properties push (fallback)."""
    if data.snapshot and data.snapshot.battery_level > 0:
        return data.snapshot.battery_level
    if data.properties and data.properties.params.items.batteryPercentage:
        return data.properties.params.items.batteryPercentage.value
    return None


def get_activity(data: MammotionLiteData) -> str | None:
    """Get mowing activity with fallback chain: event code -> snapshot -> deviceState.

    Event codes are the most timely signal during state transitions - the snapshot
    may be stale from a previous probe until the next state push arrives.
    """
    if data.last_event_code:
        activity = EVENT_CODE_TO_ACTIVITY.get(data.last_event_code)
        if activity:
            return activity
    if data.snapshot:
        activity = data.snapshot.mowing_activity
        if activity == "unknown(0)":
            return "idle"
        return activity
    if data.properties and data.properties.params.items.deviceState:
        return str(data.properties.params.items.deviceState.value)
    return None


def get_progress(data: MammotionLiteData) -> int | None:
    """Get job progress percentage from packed area field.

    The actual percentage is in the upper 16 bits of report_data.work.area.
    """
    if data.snapshot:
        area_raw = data.snapshot.raw.report_data.work.area
        if area_raw > 0:
            return area_raw >> 16
    return None


def get_last_event(data: MammotionLiteData) -> str | None:
    """Get last event label."""
    return data.last_event_label


def get_last_event_attrs(data: MammotionLiteData) -> dict[str, Any]:
    """Get last event extra attributes (code and timestamp)."""
    attrs: dict[str, Any] = {}
    if data.last_event_code:
        attrs["code"] = data.last_event_code
    if data.last_event_time:
        attrs["timestamp"] = data.last_event_time.isoformat()
    return attrs


def extract_wifi_rssi(data: MammotionLiteData) -> int | None:
    """Extract WiFi RSSI from snapshot (preferred) or networkInfo property (fallback).

    Snapshot provides wifi_rssi from report_data.connect when RPT reports are active.
    Properties push provides it in the networkInfo JSON string every 30 minutes.
    """
    # Preferred: from RPT report data (available during mowing and initial probe)
    if data.snapshot:
        try:
            rssi = data.snapshot.raw.report_data.connect.wifi_rssi
            if rssi != 0:
                return rssi
        except AttributeError:
            pass

    # Fallback: from 30-min properties push
    if not data.properties or not data.properties.params.items.networkInfo:
        return None
    try:
        network_info = data.properties.params.items.networkInfo.value
        if isinstance(network_info, str):
            parsed = json.loads(network_info)
            return parsed.get("wifi_rssi")
        if isinstance(network_info, dict):
            return network_info.get("wifi_rssi")
    except (json.JSONDecodeError, AttributeError):
        _LOGGER.debug("Failed to parse networkInfo for WiFi RSSI")
    return None


def get_blade_height(data: MammotionLiteData) -> int | None:
    """Get blade height from snapshot (preferred) or properties push (fallback)."""
    if data.snapshot and data.snapshot.blade_height > 0:
        return data.snapshot.blade_height
    if data.properties and data.properties.params.items.knifeHeight:
        return data.properties.params.items.knifeHeight.value
    return None
