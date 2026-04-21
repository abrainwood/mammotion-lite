"""Mammotion Lite - online/offline binary sensor."""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MammotionLiteConfigEntry
from .const import DOMAIN, device_info
from .runtime_data import MammotionLiteData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MammotionLiteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mammotion online/offline binary sensor."""
    data = entry.runtime_data
    async_add_entities([MammotionOnlineSensor(data, entry.entry_id)])


class MammotionOnlineSensor(BinarySensorEntity):
    """Binary sensor for mower online/offline status via MQTT push."""

    _attr_has_entity_name = True
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, data: MammotionLiteData, entry_id: str) -> None:
        """Initialize the binary sensor."""
        self._data = data
        self._attr_unique_id = f"{DOMAIN}_{data.device_name}_online"
        self._attr_device_info = device_info(entry_id, data.device_name)
        self._unregister: Callable[[], None] | None = None

    @property
    def is_on(self) -> bool:
        """Return True if the mower is online."""
        return self._data.online

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
