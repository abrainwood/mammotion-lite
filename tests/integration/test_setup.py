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


class TestInitialProbe:
    """Test the initial state probe sent on startup."""

    async def test_initial_probe_requests_all_info_types(self, hass: HomeAssistant):
        """Probe requests device status, work, location, and connectivity."""
        from pymammotion.proto import RptInfoType

        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        mock_cmd = MagicMock()
        mock_cmd_cls = MagicMock(return_value=mock_cmd)

        with _patches(
            client,
            **{"custom_components.mammotion_lite.MammotionCommand": mock_cmd_cls},
        ):
            # Patch sleep so the probe fires immediately
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        info_types = mock_cmd.request_iot_sys.call_args.kwargs["rpt_info_type"]
        assert RptInfoType.RIT_DEV_STA in info_types
        assert RptInfoType.RIT_WORK in info_types
        assert RptInfoType.RIT_DEV_LOCAL in info_types
        assert RptInfoType.RIT_CONNECT in info_types


class TestAreaNamesFetch:
    """Test area names are populated on runtime_data during startup."""

    async def test_area_names_populated_on_startup(self, hass: HomeAssistant):
        """Area names from the device end up on runtime_data.area_names."""
        from dataclasses import dataclass, field

        @dataclass
        class _AreaName:
            hash: int = 0
            name: str = ""

        @dataclass
        class _Map:
            area_name: list = field(default_factory=list)

        @dataclass
        class _FakeDevice:
            map: _Map = field(default_factory=_Map)

        client = make_mock_client()
        device_with_names = _FakeDevice(
            map=_Map(area_name=[
                _AreaName(hash=111, name="Front lawn"),
                _AreaName(hash=222, name="Back lawn"),
            ])
        )
        client.get_device_by_name = MagicMock(return_value=device_with_names)

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names == {111: "Front lawn", 222: "Back lawn"}

    async def test_unnamed_areas_get_fallback_names(self, hass: HomeAssistant):
        """Areas in map.area without names in area_name get 'Area N' fallbacks."""
        from dataclasses import dataclass, field

        @dataclass
        class _AreaName:
            hash: int = 0
            name: str = ""

        @dataclass
        class _Map:
            area_name: list = field(default_factory=list)
            area: dict = field(default_factory=dict)

        @dataclass
        class _FakeDevice:
            map: _Map = field(default_factory=_Map)

        client = make_mock_client()
        # 2 named areas + 3 unnamed (only in map.area, not in area_name)
        device = _FakeDevice(
            map=_Map(
                area_name=[
                    _AreaName(hash=111, name="Front lawn"),
                    _AreaName(hash=222, name="Side strip"),
                ],
                area={111: "boundary_data", 222: "boundary_data",
                      333: "boundary_data", 444: "boundary_data",
                      555: "boundary_data"},
            )
        )
        client.get_device_by_name = MagicMock(return_value=device)

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names[111] == "Front lawn"
        assert data.area_names[222] == "Side strip"
        # Unnamed areas should get fallback names
        assert 333 in data.area_names
        assert 444 in data.area_names
        assert 555 in data.area_names
        # Fallback names should be "Area 1", "Area 2", "Area 3"
        fallback_names = sorted([data.area_names[h] for h in [333, 444, 555]])
        assert fallback_names == ["Area 1", "Area 2", "Area 3"]

    async def test_area_names_timeout_no_crash(self, hass: HomeAssistant):
        """Area names timeout when device never returns names."""
        from dataclasses import dataclass, field

        @dataclass
        class _Map:
            area_name: list = field(default_factory=list)

        @dataclass
        class _FakeDevice:
            map: _Map = field(default_factory=_Map)

        client = make_mock_client()
        # Device exists but area_name stays empty
        client.get_device_by_name = MagicMock(return_value=_FakeDevice())

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names == {}
        assert entry.state == ConfigEntryState.LOADED

    async def test_area_names_device_not_found(self, hass: HomeAssistant):
        """Area names timeout gracefully when get_device_by_name returns None."""
        client = make_mock_client()
        client.get_device_by_name = MagicMock(return_value=None)

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names == {}
        assert entry.state == ConfigEntryState.LOADED

    async def test_map_sync_exception_no_crash(self, hass: HomeAssistant):
        """Map sync exception is caught, integration stays loaded."""
        client = make_mock_client()
        client.start_map_sync = AsyncMock(side_effect=Exception("MQTT not ready"))

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names == {}
        assert entry.state == ConfigEntryState.LOADED


class TestMapSyncRetry:
    """Test map sync retry behavior when saga fails."""

    async def test_retries_on_saga_failure_and_succeeds(self, hass: HomeAssistant):
        """Map sync retries after saga failure and loads area names on retry."""
        from dataclasses import dataclass, field

        @dataclass
        class _AreaName:
            hash: int = 0
            name: str = ""

        @dataclass
        class _Map:
            area_name: list = field(default_factory=list)

        @dataclass
        class _FakeDevice:
            map: _Map = field(default_factory=_Map)

        client = make_mock_client()
        device_with_names = _FakeDevice(
            map=_Map(area_name=[
                _AreaName(hash=111, name="Front lawn"),
            ])
        )

        # First call raises (saga failure), second succeeds
        client.start_map_sync = AsyncMock(
            side_effect=[Exception("Saga failed"), None]
        )
        client.get_device_by_name = MagicMock(return_value=device_with_names)

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names == {111: "Front lawn"}
        assert client.start_map_sync.call_count == 2

    async def test_exhausts_all_retries_gracefully(self, hass: HomeAssistant):
        """All retry attempts fail without crashing. Tries 4 times total."""
        client = make_mock_client()
        client.start_map_sync = AsyncMock(side_effect=Exception("MQTT not ready"))

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names == {}
        assert entry.state == ConfigEntryState.LOADED
        # 1 initial + 3 retries = 4 total attempts
        assert client.start_map_sync.call_count == 1 + 3

    async def test_no_mower_handle_does_not_block_map_sync(self, hass: HomeAssistant):
        """Map sync runs even when mower handle is unavailable for probe."""
        from dataclasses import dataclass, field

        @dataclass
        class _AreaName:
            hash: int = 0
            name: str = ""

        @dataclass
        class _Map:
            area_name: list = field(default_factory=list)

        @dataclass
        class _FakeDevice:
            map: _Map = field(default_factory=_Map)

        client = make_mock_client(mower_handle=None)
        device_with_names = _FakeDevice(
            map=_Map(area_name=[
                _AreaName(hash=111, name="Front lawn"),
            ])
        )
        client.get_device_by_name = MagicMock(return_value=device_with_names)

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.area_names == {111: "Front lawn"}
        client.start_map_sync.assert_called()


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
