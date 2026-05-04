"""Constants for the Mammotion Lite integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN = "mammotion_lite"

# Config keys
CONF_ACCOUNTNAME = "account_name"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_IOT_ID = "device_iot_id"

# Notification event codes from device_notification_event
# 13xx and 12xx observed with same suffix meanings. The distinction between
# the two series is unclear - cancel/dock always uses 12xx regardless of
# how the task was started. New codes may appear; unknown codes are logged
# at WARNING for investigation.
EVENT_TASK_STARTED = "1301"
EVENT_TASK_CANCELLED = "1302"
EVENT_RETURNING_TO_BASE = "1304"
EVENT_TASK_COMPLETED = "1305"
EVENT_DOCKED_CHARGING = "1307"

EVENT_STARTED_ALT = "1201"
EVENT_COMPLETED_ALT = "1205"
EVENT_DOCKED_CHARGING_ALT = "1207"

# Human-readable labels for known event codes
EVENT_CODE_LABELS: dict[str, str] = {
    "1101": "No channel to charging area",
    EVENT_TASK_STARTED: "Task started",
    "1203": "Navigation event",
    EVENT_TASK_CANCELLED: "Task cancelled",
    "1303": "Error (1303)",
    EVENT_RETURNING_TO_BASE: "Returning to base",
    EVENT_TASK_COMPLETED: "Task completed",
    "1306": "Return to base failed",
    EVENT_DOCKED_CHARGING: "Docked and charging",
    EVENT_STARTED_ALT: "Task started",
    EVENT_COMPLETED_ALT: "Arrived at base",
    EVENT_DOCKED_CHARGING_ALT: "Docked and charging",
}

# Map event codes to user-facing activity states
EVENT_CODE_TO_ACTIVITY: dict[str, str] = {
    EVENT_TASK_STARTED: "mowing",
    EVENT_STARTED_ALT: "mowing",
    EVENT_TASK_CANCELLED: "returning",
    EVENT_RETURNING_TO_BASE: "returning",
    EVENT_TASK_COMPLETED: "docked",
    EVENT_COMPLETED_ALT: "docked",
    EVENT_DOCKED_CHARGING: "charging",
    EVENT_DOCKED_CHARGING_ALT: "charging",
}

# Codes that trigger RPT_START (mower is working)
START_REPORTING_CODES: frozenset[str] = frozenset({
    EVENT_TASK_STARTED,
    EVENT_STARTED_ALT,
})

# Codes that trigger RPT_STOP (mower is done)
STOP_REPORTING_CODES: frozenset[str] = frozenset({
    EVENT_DOCKED_CHARGING,
    EVENT_DOCKED_CHARGING_ALT,
})


def device_info(entry_id: str, device_name: str) -> DeviceInfo:
    """Return consistent DeviceInfo for all entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{device_name}")},
        name=device_name,
        manufacturer="Mammotion",
    )
