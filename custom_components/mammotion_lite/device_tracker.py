"""Mammotion Lite - GPS device tracker from property push."""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MammotionLiteConfigEntry
from .const import DOMAIN, device_info
from .device_tracker_helpers import extract_coordinates
from .runtime_data import MammotionLiteData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MammotionLiteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mammotion GPS device tracker."""
    data = entry.runtime_data
    async_add_entities([MammotionDeviceTracker(data, entry.entry_id)])


class MammotionDeviceTracker(TrackerEntity):
    """Device tracker for mower location via passive coordinate pushes."""

    _attr_has_entity_name = True
    _attr_translation_key = "location"
    _attr_icon = "mdi:robot-mower"

    def __init__(self, data: MammotionLiteData, entry_id: str) -> None:
        """Initialize the device tracker."""
        self._data = data
        self._attr_unique_id = f"{DOMAIN}_{data.device_name}_location"
        self._attr_device_info = device_info(entry_id, data.device_name)
        self._latitude: float | None = None
        self._longitude: float | None = None
        self._unregister: Callable[[], None] | None = None

    @property
    def source_type(self) -> SourceType:
        """Return GPS as the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude from last coordinate push."""
        self._update_coordinates()
        return self._latitude

    @property
    def longitude(self) -> float | None:
        """Return longitude from last coordinate push."""
        self._update_coordinates()
        return self._longitude

    # ~500m in degrees at mid-latitudes. Ignores jitter from
    # competing coordinate sources (RTK base vs properties push)
    # while still tracking real movement during mowing.
    _POSITION_CHANGE_THRESHOLD_DEG = 0.005

    def _update_coordinates(self) -> None:
        """Parse and cache coordinates from latest push data.

        Applies hysteresis: small position changes (under ~500m) are
        ignored to prevent the tracker from flipping between competing
        coordinate sources when the mower is docked.
        """
        result = extract_coordinates(self._data)
        if result is None:
            return
        new_lat, new_lon = result
        if self._latitude is not None and self._longitude is not None:
            dlat = abs(new_lat - self._latitude)
            dlon = abs(new_lon - self._longitude)
            if dlat < self._POSITION_CHANGE_THRESHOLD_DEG and dlon < self._POSITION_CHANGE_THRESHOLD_DEG:
                return
        self._latitude, self._longitude = new_lat, new_lon

    async def async_added_to_hass(self) -> None:
        """Register for push updates."""

        @callback
        def _on_update() -> None:
            self.async_write_ha_state()

        self._unregister = self._data.register_update_callback(_on_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister from push updates."""
        if self._unregister:
            self._unregister()
            self._unregister = None
