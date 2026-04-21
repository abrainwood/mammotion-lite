"""Constants for the Mammotion Lite integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN = "mammotion_lite"

# Config keys
CONF_ACCOUNTNAME = "account_name"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_IOT_ID = "device_iot_id"

# Notification event codes from device_notification_event
EVENT_TASK_STARTED = "1301"
EVENT_TASK_CANCELLED = "1302"
EVENT_RETURNING_TO_BASE = "1304"
EVENT_TASK_COMPLETED = "1305"
EVENT_DOCKED_CHARGING = "1307"

# Human-readable labels for known event codes
EVENT_CODE_LABELS: dict[str, str] = {
    EVENT_TASK_STARTED: "Task started",
    EVENT_TASK_CANCELLED: "Task cancelled",
    "1303": "Error (1303)",
    EVENT_RETURNING_TO_BASE: "Returning to base",
    EVENT_TASK_COMPLETED: "Task completed",
    "1306": "Error (1306)",
    EVENT_DOCKED_CHARGING: "Docked and charging",
}

# Codes that trigger RPT_START (mower is working)
START_REPORTING_CODES: frozenset[str] = frozenset({EVENT_TASK_STARTED})

# Codes that trigger RPT_STOP (mower is done)
STOP_REPORTING_CODES: frozenset[str] = frozenset({EVENT_DOCKED_CHARGING})


def device_info(entry_id: str, device_name: str) -> DeviceInfo:
    """Return consistent DeviceInfo for all entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{device_name}")},
        name=device_name,
        manufacturer="Mammotion",
    )
