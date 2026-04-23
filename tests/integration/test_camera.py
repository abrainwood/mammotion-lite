"""Integration tests for camera.py: services, streaming state, FPV loop, placeholder image.

Tests the camera entity and its four services (refresh_stream, start_video,
stop_video, get_tokens) by setting up the full integration with real HA
platform forwarding. Services are registered under the mammotion_lite domain
and capture the config entry's runtime_data in closures.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.mammotion_lite.const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
)
from tests.conftest import make_capturing_client

PATCH_CLIENT = "custom_components.mammotion_lite.MammotionClient"
PATCH_SESSION = "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession"
PATCH_COMMAND = "custom_components.mammotion_lite.MammotionCommand"

# Camera entity ID follows the same slugification as other entities:
# unique_id = "mammotion_lite_Luba-VSLKJX_camera" -> entity_id = "camera.luba_vslkjx_camera"
CAMERA_ENTITY = "camera.luba_vslkjx_camera"


@dataclass
class FakeStreamData:
    """Mimics the stream subscription response data payload."""

    data: Any = None


@dataclass
class FakeStreamInner:
    """Mimics the inner stream data object with a to_dict method."""

    app_id: str = "test_app_id"
    token: str = "test_token"
    channel: str = "test_channel"
    uid: int = 12345

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "token": self.token,
            "channel": self.channel,
            "uid": self.uid,
        }


async def _setup(hass: HomeAssistant):
    """Set up integration with capturing client. Return (entry, client, captured, commands_mock)."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    client, captured = make_capturing_client()
    commands_mock = MagicMock()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCOUNTNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_DEVICE_NAME: "Luba-VSLKJX",
            CONF_DEVICE_IOT_ID: "abc123",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(PATCH_CLIENT, return_value=client),
        patch(PATCH_SESSION, return_value=MagicMock()),
        patch(PATCH_COMMAND, return_value=commands_mock),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert entry.state == ConfigEntryState.LOADED
    return entry, client, captured, commands_mock


class TestServicesRegistered:
    """Test that camera services are registered during setup."""

    async def test_refresh_stream_service_registered(self, hass: HomeAssistant):
        """refresh_stream service exists under mammotion_lite domain after setup."""
        await _setup(hass)
        assert hass.services.has_service(DOMAIN, "refresh_stream")

    async def test_start_video_service_registered(self, hass: HomeAssistant):
        """start_video service exists under mammotion_lite domain after setup."""
        await _setup(hass)
        assert hass.services.has_service(DOMAIN, "start_video")

    async def test_stop_video_service_registered(self, hass: HomeAssistant):
        """stop_video service exists under mammotion_lite domain after setup."""
        await _setup(hass)
        assert hass.services.has_service(DOMAIN, "stop_video")

    async def test_get_tokens_service_registered(self, hass: HomeAssistant):
        """get_tokens service exists under mammotion_lite domain after setup."""
        await _setup(hass)
        assert hass.services.has_service(DOMAIN, "get_tokens")


class TestStartVideo:
    """Test start_video service sends the join command."""

    async def test_start_video_sends_join_command(self, hass: HomeAssistant):
        """start_video calls device_agora_join_channel_with_position(enter_state=1)."""
        entry, client, captured, commands_mock = await _setup(hass)

        await hass.services.async_call(DOMAIN, "start_video", blocking=True)
        await hass.async_block_till_done()

        commands_mock.device_agora_join_channel_with_position.assert_called_with(
            enter_state=1
        )
        handle = client.mower("Luba-VSLKJX")
        handle.send_raw.assert_called()


class TestStopVideo:
    """Test stop_video service sends the leave command."""

    async def test_stop_video_sends_leave_command(self, hass: HomeAssistant):
        """stop_video calls device_agora_join_channel_with_position(enter_state=0)."""
        entry, client, captured, commands_mock = await _setup(hass)

        await hass.services.async_call(DOMAIN, "stop_video", blocking=True)
        await hass.async_block_till_done()

        commands_mock.device_agora_join_channel_with_position.assert_called_with(
            enter_state=0
        )
        handle = client.mower("Luba-VSLKJX")
        handle.send_raw.assert_called()


class TestGetTokens:
    """Test get_tokens service returns stream data."""

    async def test_get_tokens_returns_cached_stream_data(self, hass: HomeAssistant):
        """get_tokens returns cached data when cache is populated."""
        entry, client, captured, commands_mock = await _setup(hass)

        # Pre-populate cache by calling refresh_stream first
        stream_inner = FakeStreamInner()
        stream_response = FakeStreamData(data=stream_inner)
        client.get_stream_subscription = AsyncMock(return_value=stream_response)

        await hass.services.async_call(DOMAIN, "refresh_stream", blocking=True)
        await hass.async_block_till_done()

        # Reset to verify get_tokens uses cache (no new API call)
        client.get_stream_subscription.reset_mock()

        result = await hass.services.async_call(
            DOMAIN, "get_tokens", blocking=True, return_response=True
        )

        # Should not have called the API again - used cache
        client.get_stream_subscription.assert_not_called()
        assert result == {
            "app_id": "test_app_id",
            "token": "test_token",
            "channel": "test_channel",
            "uid": 12345,
        }

    async def test_get_tokens_auto_refreshes_when_cache_empty(self, hass: HomeAssistant):
        """get_tokens fetches from API when cache is empty."""
        entry, client, captured, commands_mock = await _setup(hass)

        stream_inner = FakeStreamInner()
        stream_response = FakeStreamData(data=stream_inner)
        client.get_stream_subscription = AsyncMock(return_value=stream_response)

        result = await hass.services.async_call(
            DOMAIN, "get_tokens", blocking=True, return_response=True
        )

        # Should have called the API to fetch fresh tokens
        client.get_stream_subscription.assert_awaited_once_with("Luba-VSLKJX", "abc123")
        assert result == {
            "app_id": "test_app_id",
            "token": "test_token",
            "channel": "test_channel",
            "uid": 12345,
        }

    async def test_get_tokens_returns_empty_when_api_fails(self, hass: HomeAssistant):
        """get_tokens returns empty dict when API returns no data."""
        entry, client, captured, commands_mock = await _setup(hass)

        # API returns None (failure)
        client.get_stream_subscription = AsyncMock(return_value=None)

        result = await hass.services.async_call(
            DOMAIN, "get_tokens", blocking=True, return_response=True
        )

        assert result == {}


class TestFpvRefreshLoop:
    """Test FPV refresh loop lifecycle tied to start/stop video."""

    async def test_fpv_loop_starts_on_start_video(self, hass: HomeAssistant):
        """start_video creates a background task for the FPV refresh loop."""
        entry, client, captured, commands_mock = await _setup(hass)

        # Patch the entry's background task creation to track it
        tasks_created = []
        original_create_task = entry.async_create_background_task

        def _tracking_create_task(hass, coro, name, **kwargs):
            tasks_created.append(name)
            # Actually create the task so it exists
            return original_create_task(hass, coro, name, **kwargs)

        with patch.object(entry, "async_create_background_task", side_effect=_tracking_create_task):
            await hass.services.async_call(DOMAIN, "start_video", blocking=True)
            await hass.async_block_till_done()

        fpv_tasks = [t for t in tasks_created if "fpv_refresh" in t]
        assert len(fpv_tasks) == 1, f"Expected 1 FPV task, got {fpv_tasks}"

    async def test_fpv_loop_stops_on_stop_video(self, hass: HomeAssistant):
        """stop_video cancels the FPV refresh loop task."""
        entry, client, captured, commands_mock = await _setup(hass)

        # Start video to create the FPV task
        await hass.services.async_call(DOMAIN, "start_video", blocking=True)
        await hass.async_block_till_done()

        # Stop video should cancel the task
        await hass.services.async_call(DOMAIN, "stop_video", blocking=True)
        await hass.async_block_till_done()

        # Verify streaming is off (the camera entity's state goes back to "idle")
        state = hass.states.get(CAMERA_ENTITY)
        assert state is not None, "Camera entity not found"
        assert state.state == "idle"


class TestCameraEntityState:
    """Test camera entity initial state and properties."""

    async def test_camera_not_streaming_initially(self, hass: HomeAssistant):
        """Camera entity state is 'idle' on initial setup (not streaming)."""
        await _setup(hass)

        state = hass.states.get(CAMERA_ENTITY)
        assert state is not None, "Camera entity not found after setup"
        assert state.state == "idle"

    async def test_camera_returns_placeholder_image(self, hass: HomeAssistant):
        """Camera entity returns a non-empty placeholder image."""
        await _setup(hass)

        # Use the HA camera component's image retrieval
        from homeassistant.components.camera import async_get_image

        image = await async_get_image(hass, CAMERA_ENTITY)
        assert image is not None
        assert image.content is not None
        assert len(image.content) > 0
        # Verify it's a PNG (starts with PNG magic bytes)
        assert image.content[:4] == b"\x89PNG"

    async def test_camera_streaming_after_start_video(self, hass: HomeAssistant):
        """Camera entity state is 'streaming' after start_video is called."""
        entry, client, captured, commands_mock = await _setup(hass)

        await hass.services.async_call(DOMAIN, "start_video", blocking=True)
        await hass.async_block_till_done()

        state = hass.states.get(CAMERA_ENTITY)
        assert state is not None
        assert state.state == "streaming"

    async def test_camera_idle_after_stop_video(self, hass: HomeAssistant):
        """Camera entity state returns to 'idle' after stop_video."""
        entry, client, captured, commands_mock = await _setup(hass)

        # Start then stop
        await hass.services.async_call(DOMAIN, "start_video", blocking=True)
        await hass.async_block_till_done()
        await hass.services.async_call(DOMAIN, "stop_video", blocking=True)
        await hass.async_block_till_done()

        state = hass.states.get(CAMERA_ENTITY)
        assert state is not None
        assert state.state == "idle"


class TestFpvRefreshInterval:
    """Guard the FPV refresh interval - a load-bearing architectural constant.

    The mower's video encoder auto-disables after ~60 seconds of inactivity.
    The refresh interval MUST be less than 60s to keep the camera alive.
    Setting it too low (e.g. 0) would hammer the mower with commands.
    """

    def test_fpv_refresh_interval_is_30_seconds(self):
        """FPV refresh interval must be 30 seconds.

        This value is derived from the mower's ~60s encoder timeout.
        Must be less than 60s (or camera drops) and more than a few seconds
        (or we hammer the mower). 30s gives safe margin on both sides.
        """
        from custom_components.mammotion_lite.camera import _FPV_REFRESH_INTERVAL_S

        assert _FPV_REFRESH_INTERVAL_S == 30


class TestServicesUseCurrentRuntimeData:
    """Services must read entry.runtime_data at call time, not capture it at setup.

    After a config entry reload (e.g. reconfigure credentials), the runtime_data
    is replaced with a new MammotionLiteData containing a fresh client. Services
    registered during the first setup must use the new data, not the old dead one.
    """

    async def test_start_video_uses_fresh_data_after_reload(self, hass: HomeAssistant):
        """After reload, start_video should use the new client, not the old one."""
        entry, client1, captured1, commands_mock1 = await _setup(hass)

        # Record how many commands client1 received so far
        calls_before = commands_mock1.device_agora_join_channel_with_position.call_count

        # Simulate reload: unload then re-setup with a new client
        await hass.config_entries.async_unload(entry.entry_id)

        # Create a second mock client + commands
        from tests.conftest import make_capturing_client
        client2, captured2 = make_capturing_client()
        commands_mock2 = MagicMock()
        commands_mock2.device_agora_join_channel_with_position.return_value = b"\x00"

        with patch(PATCH_CLIENT, return_value=client2), \
             patch(PATCH_COMMAND, return_value=commands_mock2), \
             patch(PATCH_SESSION):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED

        # Call start_video - it should use client2's commands, not client1's
        await hass.services.async_call(DOMAIN, "start_video", blocking=True)
        await hass.async_block_till_done()

        # client2's commands should have been called
        assert commands_mock2.device_agora_join_channel_with_position.call_count > 0, \
            "New client's commands should be used after reload"
        # client1's commands should NOT have received additional calls
        assert commands_mock1.device_agora_join_channel_with_position.call_count == calls_before, \
            "Old client's commands should not be called after reload"
