"""Event handling - extract notification codes and map to labels."""

from __future__ import annotations

import json
import logging
from typing import Any

from .const import EVENT_CODE_LABELS

_LOGGER = logging.getLogger(__name__)


def extract_event_code(event: Any) -> str | None:
    """Extract notification code from a device_notification_event.

    Args:
        event: A ThingEventMessage (or fake equivalent) with params.identifier
               and params.value.data fields.

    Returns:
        The code as a string, or None if the event is not a notification
        or the code cannot be extracted.
    """
    identifier = getattr(event.params, "identifier", None)
    value = getattr(event.params, "value", None)

    if identifier != "device_notification_event" or value is None:
        return None

    try:
        data = value.data
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            return None
        code = data.get("code")
        if code is None:
            return None
        return str(code)
    except (json.JSONDecodeError, AttributeError):
        _LOGGER.debug("Failed to parse notification event data")
        return None


def get_event_label(code: str) -> str:
    """Return a human-readable label for an event code."""
    return EVENT_CODE_LABELS.get(code, f"Unknown ({code})")
