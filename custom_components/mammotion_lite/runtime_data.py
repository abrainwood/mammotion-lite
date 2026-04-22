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

    def dispatch_sensor_update(self) -> None:
        """Record sensor data arrival and notify entities.

        Use this (not dispatch_update) for property and state pushes that
        carry actual sensor data. Events and status changes use dispatch_update.
        """
        self.last_data_update = datetime.now(timezone.utc)
        for cb in self._update_callbacks:
            cb()
