"""Mammotion Lite - sensor platform."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MammotionLiteConfigEntry
from .const import DOMAIN, device_info
from .runtime_data import MammotionLiteData
from .sensors import (
    extract_wifi_rssi,
    get_activity,
    get_battery,
    get_blade_height,
    get_last_data_update,
    get_last_event,
    get_last_event_attrs,
    get_last_event_time,
    get_progress,
    get_zone_name,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class MammotionSensorDescription(SensorEntityDescription):
    """Describes a Mammotion sensor."""

    value_fn: Callable[[MammotionLiteData], Any]
    extra_attrs_fn: Callable[[MammotionLiteData], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[MammotionSensorDescription, ...] = (
    MammotionSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=get_battery,
    ),
    MammotionSensorDescription(
        key="activity",
        translation_key="activity",
        icon="mdi:robot-mower",
        value_fn=get_activity,
    ),
    MammotionSensorDescription(
        key="job_progress",
        translation_key="job_progress",
        icon="mdi:progress-check",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=get_progress,
    ),
    MammotionSensorDescription(
        key="last_event",
        translation_key="last_event",
        icon="mdi:bell-outline",
        value_fn=get_last_event,
        extra_attrs_fn=get_last_event_attrs,
    ),
    MammotionSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=extract_wifi_rssi,
    ),
    MammotionSensorDescription(
        key="blade_height",
        translation_key="blade_height",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:grass",
        value_fn=get_blade_height,
    ),
    MammotionSensorDescription(
        key="mowing_zone",
        translation_key="mowing_zone",
        icon="mdi:map-marker-radius",
        value_fn=get_zone_name,
    ),
    MammotionSensorDescription(
        key="last_event_time",
        name="Last event time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:bell-clock-outline",
        value_fn=get_last_event_time,
    ),
    MammotionSensorDescription(
        key="last_report_time",
        name="Last report time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
        value_fn=get_last_data_update,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MammotionLiteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mammotion sensors."""
    data = entry.runtime_data
    data._add_entities_cb = async_add_entities
    data._entry_id = entry.entry_id
    async_add_entities(
        MammotionPushSensor(data, description, entry.entry_id)
        for description in SENSOR_DESCRIPTIONS
    )


class MammotionPushSensor(SensorEntity):
    """Sensor entity driven by MQTT push data."""

    _attr_has_entity_name = True
    entity_description: MammotionSensorDescription

    def __init__(
        self,
        data: MammotionLiteData,
        description: MammotionSensorDescription,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        self._data = data
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{data.device_name}_{description.key}"
        self._attr_device_info = device_info(entry_id, data.device_name)
        self._unregister: Callable[[], None] | None = None

    @property
    def native_value(self) -> Any:
        """Return the sensor value from latest data."""
        return self.entity_description.value_fn(self._data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.entity_description.extra_attrs_fn:
            return self.entity_description.extra_attrs_fn(self._data)
        return None

    async def async_added_to_hass(self) -> None:
        """Register for push updates when added to HA."""

        @callback
        def _on_update() -> None:
            self.async_write_ha_state()

        self._unregister = self._data.register_update_callback(_on_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister from push updates."""
        if self._unregister:
            self._unregister()
            self._unregister = None


class MammotionAreaSensor(SensorEntity):
    """Per-area 'last mow' timestamp sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:grass"

    def __init__(
        self,
        data: MammotionLiteData,
        area_hash: int,
        area_name: str,
        entry_id: str,
    ) -> None:
        """Initialize the area sensor."""
        self._data = data
        self._area_hash = area_hash
        slug = area_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{data.device_name}_last_mow_{slug}"
        self._attr_name = f"Last mow - {area_name}"
        self._attr_device_info = device_info(entry_id, data.device_name)
        self._unregister: Callable[[], None] | None = None

    @property
    def native_value(self) -> Any:
        """Return the last mow timestamp for this area."""
        return self._data.mow_history.get(self._area_hash)

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
