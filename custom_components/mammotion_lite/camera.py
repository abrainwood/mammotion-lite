"""Mammotion Lite - camera entity with Agora client-side streaming.

The actual video streaming is handled by the custom Lovelace card (www/agora-client.js)
which loads the Agora JS SDK in the browser. This module provides:
- A camera entity (placeholder image when not streaming)
- Services for the JS card: refresh_stream, start_video, stop_video, get_tokens
- A background FPV refresh loop that keeps the mower's video encoder alive
"""

from __future__ import annotations

import asyncio
import functools
import logging
import secrets
from pathlib import Path
from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MammotionLiteConfigEntry
from .const import DOMAIN, device_info
from .runtime_data import MammotionLiteData

# The mower's video encoder times out after ~60s without activity.
# Sending refresh_fpv periodically keeps it alive.
_FPV_REFRESH_INTERVAL_S = 30

_LOGGER = logging.getLogger(__name__)

PLACEHOLDER = Path(__file__).parent / "placeholder.png"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MammotionLiteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Mammotion camera entity and services."""
    data = entry.runtime_data
    camera = MammotionCamera(data, entry.entry_id)
    async_add_entities([camera])
    await _async_setup_services(hass, entry, camera)


class MammotionCamera(Camera):
    """Camera entity for Mammotion mower.

    Shows a placeholder image. Live streaming is handled by the
    custom Agora Lovelace card (camera-agora-card) in the browser.
    """

    _attr_has_entity_name = True
    _attr_name = "Camera"

    def __init__(self, data: MammotionLiteData, entry_id: str) -> None:
        """Initialize the camera entity."""
        super().__init__()
        self._data = data
        self._attr_unique_id = f"{DOMAIN}_{data.device_name}_camera"
        self._attr_device_info = device_info(entry_id, data.device_name)
        self.access_tokens = [secrets.token_hex(16)]
        self._streaming = False

    @property
    def is_streaming(self) -> bool:
        """Return True if the camera is actively streaming."""
        return self._streaming

    def set_streaming(self, streaming: bool) -> None:
        """Update streaming state and notify HA."""
        self._streaming = streaming
        self.schedule_update_ha_state()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a placeholder image."""
        return await self.hass.async_add_executor_job(self._placeholder_image)

    @classmethod
    @functools.cache
    def _placeholder_image(cls) -> bytes:
        """Return cached placeholder image bytes."""
        if PLACEHOLDER.exists():
            return PLACEHOLDER.read_bytes()
        return b""


async def _async_setup_services(
    hass: HomeAssistant, entry: MammotionLiteConfigEntry, camera: MammotionCamera
) -> None:
    """Register services for the Agora JS card."""
    data = entry.runtime_data
    _stream_cache: dict[str, Any] = {}
    _fpv_task: asyncio.Task | None = None

    async def _fpv_refresh_loop() -> None:
        """Periodically send refresh_fpv to keep the mower's video encoder alive.

        The mower's video encoder automatically disables itself after ~60s
        of inactivity. This loop re-enables it every 30s while the camera
        is active.
        """
        _LOGGER.debug("FPV refresh loop started for %s", data.device_name)
        try:
            while True:
                await asyncio.sleep(_FPV_REFRESH_INTERVAL_S)
                handle = data.client.mower(data.device_name)
                if handle is None:
                    continue
                try:
                    command = data.commands.refresh_fpv()
                    await handle.send_raw(command)
                    _LOGGER.debug("FPV refresh sent for %s", data.device_name)
                except Exception:
                    _LOGGER.warning("FPV refresh failed for %s", data.device_name, exc_info=True)
        except asyncio.CancelledError:
            _LOGGER.debug("FPV refresh loop cancelled for %s", data.device_name)
            raise

    async def handle_refresh_stream(call: ServiceCall) -> None:
        """Refresh stream subscription tokens from Mammotion cloud."""
        stream_data = await data.client.get_stream_subscription(
            data.device_name, data.iot_id
        )
        if stream_data and stream_data.data:
            _stream_cache["data"] = stream_data.data
            _LOGGER.debug("Stream tokens refreshed for %s", data.device_name)
        else:
            _LOGGER.warning("Failed to refresh stream tokens for %s", data.device_name)

    async def handle_start_video(call: ServiceCall) -> None:
        """Tell the mower to join the Agora video channel and start FPV refresh."""
        nonlocal _fpv_task
        handle = data.client.mower(data.device_name)
        if handle is None:
            _LOGGER.warning("No mower handle for start_video")
            return
        try:
            command = data.commands.device_agora_join_channel_with_position(enter_state=1)
            await handle.send_raw(command)
            _LOGGER.debug("Mower joined video channel")
            camera.set_streaming(True)

            # Start FPV refresh loop to keep encoder alive
            if _fpv_task is None or _fpv_task.done():
                _fpv_task = entry.async_create_background_task(
                    hass, _fpv_refresh_loop(), f"{DOMAIN}_fpv_refresh"
                )
        except Exception:
            _LOGGER.warning("Failed to send start_video command", exc_info=True)

    async def handle_stop_video(call: ServiceCall) -> None:
        """Tell the mower to leave the Agora video channel and stop FPV refresh."""
        nonlocal _fpv_task
        # Stop FPV refresh loop
        if _fpv_task and not _fpv_task.done():
            _fpv_task.cancel()
            _fpv_task = None

        camera.set_streaming(False)

        handle = data.client.mower(data.device_name)
        if handle is None:
            return
        try:
            command = data.commands.device_agora_join_channel_with_position(enter_state=0)
            await handle.send_raw(command)
            _LOGGER.debug("Mower left video channel")
        except Exception:
            _LOGGER.warning("Failed to send stop_video command", exc_info=True)

    async def handle_get_tokens(call: ServiceCall) -> ServiceResponse:
        """Return Agora token data for the JS card."""
        if "data" not in _stream_cache:
            stream_data = await data.client.get_stream_subscription(
                data.device_name, data.iot_id
            )
            if stream_data and stream_data.data:
                _stream_cache["data"] = stream_data.data

        stream = _stream_cache.get("data")
        if stream is None:
            return {}

        return stream.to_dict()

    if not hass.services.has_service(DOMAIN, "refresh_stream"):
        hass.services.async_register(DOMAIN, "refresh_stream", handle_refresh_stream)
        hass.services.async_register(DOMAIN, "start_video", handle_start_video)
        hass.services.async_register(DOMAIN, "stop_video", handle_stop_video)
        hass.services.async_register(
            DOMAIN,
            "get_tokens",
            handle_get_tokens,
            supports_response=SupportsResponse.ONLY,
        )
        _LOGGER.debug("Camera services registered for %s", DOMAIN)
