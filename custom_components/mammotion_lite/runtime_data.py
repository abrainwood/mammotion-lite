"""Runtime data container for Mammotion Lite integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class MammotionLiteData:
    """Runtime data stored on the config entry."""

    client: Any  # MammotionClient
    commands: Any  # MammotionCommand
    device_name: str
    iot_id: str
    properties: Any | None = None  # ThingPropertiesMessage
    snapshot: Any | None = None  # DeviceSnapshot
    online: bool = False
    reporting_active: bool = False
    last_report_time: float = 0.0
    last_event_code: str | None = None
    last_event_label: str | None = None
    last_event_time: datetime | None = None
    last_data_update: datetime | None = None
    area_names: dict[int, str] = field(default_factory=dict)
    mow_history: dict[int, datetime] = field(default_factory=dict)
    last_progress: int = 0
    current_zone_hash: int = 0
    active_zone_hashs: list[int] = field(default_factory=list)
    _add_entities_cb: Any | None = None
    _entry_id: str = ""
    _subscriptions: list[Any] = field(default_factory=list)
    _update_callbacks: list[Callable[[], None]] = field(default_factory=list)
    _keepalive_task: asyncio.Task | None = None

    def register_update_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Register callback for push data updates. Returns unregister function."""
        self._update_callbacks.append(cb)

        def _unregister() -> None:
            self._update_callbacks.remove(cb)

        return _unregister

    def dispatch_update(self) -> None:
        """Notify all registered entities of new data."""
        for cb in self._update_callbacks:
            cb()

    def create_area_sensors(self) -> None:
        """Create per-area 'last mow' sensors from area_names.

        Called after area names are loaded (asynchronously, post-setup).
        Uses the async_add_entities callback stored during sensor platform setup.
        """
        if not self._add_entities_cb or not self.area_names:
            return

        from .sensor import MammotionAreaSensor

        entities = [
            MammotionAreaSensor(self, area_hash, area_name, self._entry_id)
            for area_hash, area_name in self.area_names.items()
        ]
        self._add_entities_cb(entities)

    def dispatch_sensor_update(self) -> None:
        """Record sensor data arrival and notify entities.

        Use this (not dispatch_update) for property and state pushes that
        carry actual sensor data. Events and status changes use dispatch_update.
        """
        now = datetime.now(timezone.utc)
        self.last_data_update = now.replace(second=0, microsecond=0)
        for cb in self._update_callbacks:
            cb()
