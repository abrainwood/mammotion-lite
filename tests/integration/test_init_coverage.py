"""Integration tests for __init__.py uncovered paths.

Covers error paths, edge cases, and cleanup logic not exercised
by the main setup/lifecycle tests:
- RPT_START/RPT_STOP when handle is None or command raises
- Keepalive loop renewal and skip logic
- Cloud retry when login fails during setup
- Event handling for unknown codes and missing notification codes
- Initial probe when handle is None or command fails
- Unload cleanup: subscriptions cancelled, watchers torn down, keepalive cancelled
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from custom_components.mammotion_lite import (
    _keepalive_loop,
    _send_rpt_start,
    _send_rpt_stop,
)
from custom_components.mammotion_lite.const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
)
from custom_components.mammotion_lite.runtime_data import MammotionLiteData
from tests.conftest import (
    FakeLoginInfo,
    FakeSubscription,
    make_capturing_client,
    make_data,
    make_event_message,
    make_mock_client,
)

PATCH_CLIENT = "custom_components.mammotion_lite.MammotionClient"
PATCH_SESSION = "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession"
PATCH_PLATFORMS = "custom_components.mammotion_lite.PLATFORMS"
PATCH_COMMAND = "custom_components.mammotion_lite.MammotionCommand"


def _make_config_entry(hass: HomeAssistant):
    """Create a MockConfigEntry for mammotion_lite."""
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


# ---------------------------------------------------------------------------
# RPT_START error paths (lines 54-55, 74-75)
# ---------------------------------------------------------------------------


class TestRptStartErrors:
    """Test _send_rpt_start error handling."""

    async def test_rpt_start_handle_is_none(self):
        """RPT_START returns early when mower handle is None (line 54-55)."""
        data = make_data(client=make_mock_client(mower_handle=None))

        await _send_rpt_start(data)

        # reporting_active should NOT be set - the function returned early
        assert data.reporting_active is False

    async def test_rpt_start_command_raises_exception(self):
        """RPT_START logs warning when send_raw raises (line 74-75)."""
        client = make_mock_client()
        handle = client.mower("anything")
        handle.send_raw = AsyncMock(side_effect=Exception("Connection lost"))

        data = make_data(client=client)

        await _send_rpt_start(data)

        # reporting_active should remain False - the exception was caught
        assert data.reporting_active is False


# ---------------------------------------------------------------------------
# RPT_STOP error paths (lines 82, 96-97)
# ---------------------------------------------------------------------------


class TestRptStopErrors:
    """Test _send_rpt_stop error handling."""

    async def test_rpt_stop_handle_is_none(self):
        """RPT_STOP returns early when mower handle is None (line 82)."""
        data = make_data(client=make_mock_client(mower_handle=None))
        data.reporting_active = True

        await _send_rpt_stop(data)

        # reporting_active should still be True - function returned before clearing it
        assert data.reporting_active is True

    async def test_rpt_stop_command_raises_exception(self):
        """RPT_STOP logs warning when send_raw raises (line 96-97)."""
        client = make_mock_client()
        handle = client.mower("anything")
        handle.send_raw = AsyncMock(side_effect=Exception("Timeout"))

        data = make_data(client=client)
        data.reporting_active = True

        await _send_rpt_stop(data)

        # reporting_active should still be True - exception prevented clearing it
        assert data.reporting_active is True
        # snapshot should also remain (not cleared because exception was before clearing)
        assert data.snapshot is None  # it was already None


# ---------------------------------------------------------------------------
# Keepalive loop (lines 106-109)
# ---------------------------------------------------------------------------


class TestKeepaliveLoop:
    """Test _keepalive_loop renewal and skip logic."""

    async def test_keepalive_renews_rpt_start_when_active(self):
        """Keepalive sends RPT_START when reporting_active is True (line 108-109)."""
        client = make_mock_client()
        data = make_data(client=client)
        data.reporting_active = True

        call_count = 0

        async def _fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                # CancelledError is caught by _keepalive_loop internally,
                # so the function returns normally after this.
                raise asyncio.CancelledError()

        with patch("custom_components.mammotion_lite.asyncio.sleep", side_effect=_fake_sleep):
            await _keepalive_loop(data)

        # send_raw was called by the first iteration (reporting_active=True)
        handle = client.mower("anything")
        assert handle.send_raw.await_count >= 1

    async def test_keepalive_skips_when_reporting_inactive(self):
        """Keepalive skips RPT_START when reporting_active is False (line 106-107)."""
        client = make_mock_client()
        data = make_data(client=client)
        data.reporting_active = False

        call_count = 0

        async def _fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()

        with patch("custom_components.mammotion_lite.asyncio.sleep", side_effect=_fake_sleep):
            await _keepalive_loop(data)

        # send_raw should NOT have been called - loop skipped due to reporting_active=False
        handle = client.mower("anything")
        handle.send_raw.assert_not_awaited()


# ---------------------------------------------------------------------------
# Cloud retry / setup error paths (lines 135-137, 182-191, 195-196)
# ---------------------------------------------------------------------------


class TestCloudRetryPaths:
    """Test cloud login failure and retry scheduling."""

    async def test_login_succeeds_but_no_session_data(self, hass: HomeAssistant):
        """Setup retries when login succeeds but mammotion_http is None (line 181-191)."""
        client = make_mock_client()
        # Login succeeds but no HTTP session data
        client.mammotion_http = None

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            result = await hass.config_entries.async_setup(entry.entry_id)

        assert result is True
        assert entry.state == ConfigEntryState.LOADED
        # runtime_data should still be created for retry
        assert isinstance(entry.runtime_data, MammotionLiteData)

    async def test_login_succeeds_but_login_info_is_none(self, hass: HomeAssistant):
        """Setup retries when login_info is None despite mammotion_http existing (line 181)."""
        client = make_mock_client()
        client.mammotion_http = MagicMock()
        client.mammotion_http.login_info = None

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            result = await hass.config_entries.async_setup(entry.entry_id)

        assert result is True
        assert entry.state == ConfigEntryState.LOADED
        assert isinstance(entry.runtime_data, MammotionLiteData)

    async def test_user_account_not_a_number_defaults_to_zero(self, hass: HomeAssistant):
        """user_account falls back to 0 when it's not parseable (line 195-196)."""
        client = make_mock_client()
        client.mammotion_http.login_info = FakeLoginInfo()
        client.mammotion_http.login_info.userInformation.userAccount = "not_a_number"

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        mock_cmd_cls = MagicMock()
        with _patches(
            client,
            **{PATCH_COMMAND: mock_cmd_cls},
        ):
            result = await hass.config_entries.async_setup(entry.entry_id)

        assert result is True
        mock_cmd_cls.assert_called_once_with("Luba-VSLKJX", user_account=0)

    async def test_cloud_retry_succeeds_after_initial_failure(self, hass: HomeAssistant):
        """Cloud retry wires subscriptions when the retry login succeeds (line 328-351)."""
        client = make_mock_client(login_succeeds=False)
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)

        # Now simulate the retry succeeding
        data = entry.runtime_data
        data.client.login_and_initiate_cloud = AsyncMock()
        data.client.mammotion_http = MagicMock()
        data.client.mammotion_http.login_info = FakeLoginInfo()

        # Import _cloud_retry and run it directly (skip the 60s sleep)
        from custom_components.mammotion_lite import _cloud_retry

        with patch("custom_components.mammotion_lite.asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession",
                return_value=MagicMock(),
            ):
                await _cloud_retry(hass, entry)

        # Subscriptions should now be wired
        data.client.setup_device_watchers.assert_called()

    async def test_cloud_retry_fails_again(self, hass: HomeAssistant):
        """Cloud retry logs warning when the retry also fails (line 350-351)."""
        client = make_mock_client(login_succeeds=False)
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)

        # Retry also fails
        data = entry.runtime_data
        data.client.login_and_initiate_cloud = AsyncMock(
            side_effect=Exception("Still down")
        )

        from custom_components.mammotion_lite import _cloud_retry

        with patch("custom_components.mammotion_lite.asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession",
                return_value=MagicMock(),
            ):
                # Should not raise - error is caught and logged
                await _cloud_retry(hass, entry)

        # Integration should still be loaded (not crashed)
        assert entry.state == ConfigEntryState.LOADED

    async def test_cloud_retry_no_session_data_after_login(self, hass: HomeAssistant):
        """Cloud retry handles login succeeding but no session data (line 348-349)."""
        client = make_mock_client(login_succeeds=False)
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)

        data = entry.runtime_data
        data.client.login_and_initiate_cloud = AsyncMock()
        data.client.mammotion_http = None  # Login succeeded but no HTTP session

        from custom_components.mammotion_lite import _cloud_retry

        with patch("custom_components.mammotion_lite.asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "custom_components.mammotion_lite.aiohttp_client.async_get_clientsession",
                return_value=MagicMock(),
            ):
                await _cloud_retry(hass, entry)

        # No crash, subscriptions NOT wired
        data.client.setup_device_watchers.assert_not_called()


# ---------------------------------------------------------------------------
# Event handling branches (lines 216-217, 234-235, 293-294)
# ---------------------------------------------------------------------------


class TestEventHandlingBranches:
    """Test event handler edge cases."""

    async def _setup_with_captured_callbacks(self, hass: HomeAssistant):
        """Set up integration and return (entry, captured)."""
        client, captured = make_capturing_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with (
            patch(PATCH_CLIENT, return_value=client),
            patch(PATCH_SESSION, return_value=MagicMock()),
            patch(PATCH_COMMAND, return_value=MagicMock()),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED
        return entry, captured

    async def test_unknown_event_code_sets_last_event(self, hass: HomeAssistant):
        """Unknown event code is stored and dispatched (lines 275-278)."""
        entry, captured = await self._setup_with_captured_callbacks(hass)

        # Send an event with a code not in EVENT_CODE_LABELS
        await captured.on_event(make_event_message(code="9999"))
        await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.last_event_code == "9999"
        assert data.last_event_label == "Unknown (9999)"

    async def test_event_no_notification_code(self, hass: HomeAssistant):
        """Event without a notification code logs identifier and skips (line 293-294)."""
        entry, captured = await self._setup_with_captured_callbacks(hass)

        # Event with a non-notification identifier (no code in extract_event_code)
        event = make_event_message(identifier="some_other_event", code=None)
        await captured.on_event(event)
        await hass.async_block_till_done()

        data = entry.runtime_data
        # last_event_code should NOT be set - this branch logs and skips
        assert data.last_event_code is None

    async def test_event_with_malformed_value_data(self, hass: HomeAssistant):
        """Event with unparseable value.data doesn't crash (extract returns None)."""
        entry, captured = await self._setup_with_captured_callbacks(hass)

        # Build an event with invalid JSON in value.data
        from tests.conftest import FakeEventParams, FakeEventValue, FakeThingEventMessage

        event = FakeThingEventMessage(
            params=FakeEventParams(
                identifier="device_notification_event",
                value=FakeEventValue(data="not valid json {{{"),
            )
        )
        await captured.on_event(event)
        await hass.async_block_till_done()

        data = entry.runtime_data
        # extract_event_code returns None for malformed data - no crash
        assert data.last_event_code is None

    async def test_event_with_no_value(self, hass: HomeAssistant):
        """Event where params.value is None hits the no-code branch."""
        entry, captured = await self._setup_with_captured_callbacks(hass)

        from tests.conftest import FakeEventParams, FakeThingEventMessage

        event = FakeThingEventMessage(
            params=FakeEventParams(
                identifier="device_notification_event",
                value=None,
            )
        )
        await captured.on_event(event)
        await hass.async_block_till_done()

        data = entry.runtime_data
        assert data.last_event_code is None


# ---------------------------------------------------------------------------
# Subscription wiring edge cases (lines 293-294, 314)
# ---------------------------------------------------------------------------


class TestSubscriptionWiringEdgeCases:
    """Test subscription wiring when mower handle is None."""

    async def test_no_mower_handle_skips_state_changed_subscription(
        self, hass: HomeAssistant
    ):
        """When client.mower() returns None, state_changed sub is skipped (line 314)."""
        client = make_mock_client(mower_handle=None)
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            result = await hass.config_entries.async_setup(entry.entry_id)

        assert result is True
        data = entry.runtime_data
        # Only 3 subscriptions (properties, status, event) - no state_changed
        assert len(data._subscriptions) == 3


# ---------------------------------------------------------------------------
# Initial probe edge cases (lines 328-351)
# ---------------------------------------------------------------------------


class TestInitialProbe:
    """Test initial probe error paths."""

    async def test_initial_probe_handle_is_none(self, hass: HomeAssistant):
        """Initial probe returns early when mower handle is None (line 215-217)."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        # During setup, handle exists. But during the delayed probe, it returns None.
        call_count = 0
        original_mower = client.mower

        def _mower_side_effect(name):
            nonlocal call_count
            call_count += 1
            # First calls are during setup_subscriptions. After that, probe gets None.
            if call_count > 2:
                return None
            return original_mower(name)

        client.mower = MagicMock(side_effect=_mower_side_effect)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        # No crash - the probe gracefully handled None handle
        assert entry.state == ConfigEntryState.LOADED

    async def test_initial_probe_send_raw_fails(self, hass: HomeAssistant):
        """Initial probe doesn't crash when send_raw raises (line 234-235)."""
        client = make_mock_client()
        handle = client.mower("anything")
        # send_raw fails during the probe
        handle.send_raw = AsyncMock(side_effect=Exception("Probe failed"))

        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        # No crash - the probe caught the exception
        assert entry.state == ConfigEntryState.LOADED


# ---------------------------------------------------------------------------
# Unload cleanup (lines 373-374, 378-379)
# ---------------------------------------------------------------------------


class TestUnloadCleanup:
    """Test unload cleanup paths."""

    async def test_unload_cancels_keepalive_task(self, hass: HomeAssistant):
        """Unload cancels the keepalive task if it's running."""
        client, captured = make_capturing_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with (
            patch(PATCH_CLIENT, return_value=client),
            patch(PATCH_SESSION, return_value=MagicMock()),
            patch(PATCH_COMMAND, return_value=MagicMock()),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        data = entry.runtime_data

        # Simulate keepalive running by starting it via a "task started" event
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()

        assert data._keepalive_task is not None
        keepalive_task = data._keepalive_task

        with (
            patch(PATCH_CLIENT, return_value=client),
            patch(PATCH_SESSION, return_value=MagicMock()),
            patch(PATCH_COMMAND, return_value=MagicMock()),
        ):
            await hass.config_entries.async_unload(entry.entry_id)

        # Allow cancellation to propagate through the event loop
        await hass.async_block_till_done()

        # Keepalive task should have been cancelled or completed (it catches CancelledError)
        assert keepalive_task.done()

    async def test_unload_sends_rpt_stop_when_reporting_active(self, hass: HomeAssistant):
        """Unload sends RPT_STOP if reporting was active."""
        client, captured = make_capturing_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with (
            patch(PATCH_CLIENT, return_value=client),
            patch(PATCH_SESSION, return_value=MagicMock()),
            patch(PATCH_COMMAND, return_value=MagicMock()),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        data = entry.runtime_data

        # Start reporting
        await captured.on_event(make_event_message(code="1301"))
        await hass.async_block_till_done()
        assert data.reporting_active is True

        # Reset mock to track unload-time calls
        data.commands.request_iot_sys.reset_mock()

        with (
            patch(PATCH_CLIENT, return_value=client),
            patch(PATCH_SESSION, return_value=MagicMock()),
            patch(PATCH_COMMAND, return_value=MagicMock()),
        ):
            await hass.config_entries.async_unload(entry.entry_id)

        # RPT_STOP should have been called during unload
        from pymammotion.proto import RptAct

        stop_calls = [
            c for c in data.commands.request_iot_sys.call_args_list
            if c.kwargs.get("rpt_act") == RptAct.RPT_STOP
        ]
        assert len(stop_calls) >= 1

    async def test_unload_teardown_watchers_raises(self, hass: HomeAssistant):
        """Unload handles teardown_device_watchers raising (line 373-374)."""
        client = make_mock_client()
        client.teardown_device_watchers = MagicMock(
            side_effect=Exception("Teardown failed")
        )
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)
            result = await hass.config_entries.async_unload(entry.entry_id)

        # Unload still succeeds despite teardown error
        assert result is True

    async def test_unload_client_stop_raises(self, hass: HomeAssistant):
        """Unload handles client.stop() raising (line 378-379)."""
        client = make_mock_client()
        client.stop = AsyncMock(side_effect=Exception("Stop failed"))
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)
            result = await hass.config_entries.async_unload(entry.entry_id)

        # Unload still succeeds despite stop error
        assert result is True

    async def test_unload_clears_subscriptions_list(self, hass: HomeAssistant):
        """Unload clears the subscriptions list after cancelling them."""
        client = make_mock_client()
        entry = _make_config_entry(hass)
        entry.add_to_hass(hass)

        with _patches(client):
            await hass.config_entries.async_setup(entry.entry_id)

        data = entry.runtime_data
        assert len(data._subscriptions) > 0

        with _patches(client):
            await hass.config_entries.async_unload(entry.entry_id)

        assert len(data._subscriptions) == 0
