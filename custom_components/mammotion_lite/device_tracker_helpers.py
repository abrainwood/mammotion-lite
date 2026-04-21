"""Device tracker coordinate extraction for Mammotion Lite."""

from __future__ import annotations

import json
import logging
from typing import Any

from .runtime_data import MammotionLiteData

_LOGGER = logging.getLogger(__name__)


def extract_coordinates(data: MammotionLiteData) -> tuple[float, float] | None:
    """Extract GPS coordinates from properties push.

    Returns (lat, lon) tuple or None if coordinates are unavailable or invalid.
    Filters out near-zero coordinates (abs < 0.01 for BOTH) as invalid.
    """
    if not data.properties or not data.properties.params.items.coordinate:
        return None

    try:
        coord_value = data.properties.params.items.coordinate.value
        if isinstance(coord_value, str):
            coord = json.loads(coord_value)
        elif isinstance(coord_value, dict):
            coord = coord_value
        else:
            return None

        lat = coord.get("lat")
        lon = coord.get("lon")

        if lat is None or lon is None:
            return None

        # Filter out near-zero coordinates (both must be near zero to be invalid)
        if abs(lat) < 0.01 and abs(lon) < 0.01:
            return None

        return (float(lat), float(lon))

    except (json.JSONDecodeError, ValueError, TypeError):
        _LOGGER.debug("Failed to parse coordinate data")
        return None
