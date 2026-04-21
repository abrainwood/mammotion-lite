"""Integration tests for mammotion_lite setup and teardown."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from custom_components.mammotion_lite.const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
)
from custom_components.mammotion_lite.runtime_data import MammotionLiteData
from tests.conftest import FakeLoginInfo, FakeSubscription, make_mock_client

PATCH_CLIENT = "custom_components.mammotion_lite.MammotionClient"
PATCH_SESSION = "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession"
PATCH_PLATFORMS = "custom_components.mammotion_lite.PLATFORMS"


def _make_config_entry(hass: HomeAssistant) -> MagicMock:
    """Create a mock config entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCOUNTNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_DEVICE_NAME: "Luba-VSLKJX",
            CONF_DEVICE_IOT_ID: "abc123",
        },
    )


def _patches(client, **extra_patches):
    """Return a combined context manager for standard patches."""
    from contextlib import ExitStack

    class _PatchStack:
        def __init__(self):
            self._stack = ExitStack()

        def __enter__(self):
            self._stack.enter_context(patch(PATCH_CLIENT, return_value=client))
            self._stack.enter_context(patch(PATCH_SESSION, return_value=MagicMock()))
            self._stack.enter_context(patch(PATCH_PLATFORMS, []))
            for target, value in extra_patches.items():
                self._stack.enter_context(patch(target, value))
            return self

        def __exit__(self, *args):
            return self._stack.__exit__(*args)

    return _PatchStack()


class TestAsyncSetupEntry:
    """Test async_setup_entry."""

    async def test_successful_setup_creates_runtime_data(self, hass: HomeAssistant):
        """Successful setup stores MammotionLiteData on the entry."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            result = await hass.config_entries.async_setup(entry.entry_id)

        assert result is True
        assert entry.state == ConfigEntryState.LOADED
        assert isinstance(entry.runtime_data, MammotionLiteData)
        assert entry.runtime_data.device_name == "Luba-VSLKJX"
        assert entry.runtime_data.iot_id == "abc123"

    async def test_setup_subscribes_to_all_channels(self, hass: HomeAssistant):
        """Setup subscribes to properties, status, events, and state_changed."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)

        client.subscribe_device_properties.assert_called_once()
        client.subscribe_device_status.assert_called_once()
        client.subscribe_device_event.assert_called_once()
        client.setup_device_watchers.assert_called_once_with("Luba-VSLKJX")

        handle = client.mower("Luba-VSLKJX")
        handle.subscribe_state_changed.assert_called_once()

    async def test_setup_stores_subscriptions_for_cleanup(self, hass: HomeAssistant):
        """All subscriptions are stored on runtime_data for teardown."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)

        data = entry.runtime_data
        # 4 subscriptions: properties, status, event, state_changed
        assert len(data._subscriptions) == 4

    async def test_setup_converts_user_account_to_int(self, hass: HomeAssistant):
        """user_account is converted to int for MammotionCommand."""
        client = make_mock_client()
        client.mammotion_http.login_info = FakeLoginInfo()
        client.mammotion_http.login_info.userInformation.userAccount = "98765"
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        mock_cmd_cls = MagicMock()
        with _patches(
            client,
            **{"custom_components.mammotion_lite.MammotionCommand": mock_cmd_cls},
        ):
            await hass.config_entries.async_setup(entry.entry_id)

        mock_cmd_cls.assert_called_once_with("Luba-VSLKJX", user_account=98765)


class TestAsyncUnloadEntry:
    """Test async_unload_entry."""

    async def test_unload_cancels_subscriptions(self, hass: HomeAssistant):
        """Unload cancels all stored subscriptions."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)

        data = entry.runtime_data
        subs = list(data._subscriptions)

        await hass.config_entries.async_unload(entry.entry_id)

        for sub in subs:
            assert sub._cancelled

    async def test_unload_tears_down_device_watchers(self, hass: HomeAssistant):
        """Unload calls teardown_device_watchers."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.config_entries.async_unload(entry.entry_id)

        client.teardown_device_watchers.assert_called_with("Luba-VSLKJX")

    async def test_unload_stops_client(self, hass: HomeAssistant):
        """Unload stops the Mammotion client."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.config_entries.async_unload(entry.entry_id)

        client.stop.assert_awaited()


class TestCloudRetry:
    """Test graceful handling of cloud connection failures."""

    async def test_cloud_failure_does_not_fail_integration(self, hass: HomeAssistant):
        """Transient cloud failure results in retry, not integration failure."""
        client = make_mock_client(login_succeeds=False)
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            result = await hass.config_entries.async_setup(entry.entry_id)

        # Integration should be loaded (not failed) - it retries in background
        assert result is True
        assert entry.state == ConfigEntryState.LOADED
