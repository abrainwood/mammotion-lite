"""Tests for mammotion_lite config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mammotion_lite.const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
)
from tests.conftest import FakeDevice, FakeLoginInfo, make_mock_client

# All tests patch MammotionClient at the config_flow import location
PATCH_CLIENT = "custom_components.mammotion_lite.config_flow.MammotionClient"


@pytest.fixture
def flow(hass: HomeAssistant):
    """Return a started config flow."""

    async def _start():
        return await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

    return _start


async def test_user_step_shows_form(hass: HomeAssistant, flow):
    """Initial step shows login form with email and password fields."""
    result = await flow()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert CONF_ACCOUNTNAME in result["data_schema"].schema
    assert CONF_PASSWORD in result["data_schema"].schema


async def test_login_success_single_device(hass: HomeAssistant, flow):
    """Successful login with one device creates entry directly."""
    client = make_mock_client(devices=[FakeDevice(device_name="Luba-VSLKJX", iot_id="abc123")])

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Luba-VSLKJX"
    assert result["data"][CONF_ACCOUNTNAME] == "user@example.com"
    assert result["data"][CONF_PASSWORD] == "secret"
    assert result["data"][CONF_DEVICE_NAME] == "Luba-VSLKJX"
    assert result["data"][CONF_DEVICE_IOT_ID] == "abc123"


async def test_login_success_multiple_devices_shows_selection(hass: HomeAssistant, flow):
    """Successful login with multiple devices shows device selection step."""
    devices = [
        FakeDevice(device_name="Luba-VSAAAA", iot_id="id1"),
        FakeDevice(device_name="Luba-VSBBBB", iot_id="id2"),
    ]
    client = make_mock_client(devices=devices)

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_device"


async def test_device_selection_creates_entry(hass: HomeAssistant, flow):
    """Selecting a device from the list creates the entry."""
    devices = [
        FakeDevice(device_name="Luba-VSAAAA", iot_id="id1"),
        FakeDevice(device_name="Luba-VSBBBB", iot_id="id2"),
    ]
    client = make_mock_client(devices=devices)

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )
        # Now select device
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_DEVICE_NAME: "Luba-VSBBBB"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_NAME] == "Luba-VSBBBB"
    assert result["data"][CONF_DEVICE_IOT_ID] == "id2"


async def test_login_failure_shows_cannot_connect(hass: HomeAssistant, flow):
    """Network error during login shows cannot_connect error."""
    client = make_mock_client(login_succeeds=False)

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_login_success_but_no_session_shows_invalid_auth(hass: HomeAssistant, flow):
    """Login succeeds but no login_info means invalid credentials."""
    client = make_mock_client()
    client.mammotion_http.login_info = None

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_no_compatible_devices_shows_error(hass: HomeAssistant, flow):
    """Login with no Luba/Yuka devices shows no_devices error."""
    client = make_mock_client(devices=[FakeDevice(device_name="RTK-Station1", iot_id="rtk1")])

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "no_devices"


async def test_luba1_devices_are_filtered_out(hass: HomeAssistant, flow):
    """Luba1 devices (no camera) are excluded from device list."""
    devices = [
        FakeDevice(device_name="Luba-VSLKJX", iot_id="good"),  # Luba 2 - has camera
        FakeDevice(device_name="Luba-0000", iot_id="luba1"),  # Luba 1 - no camera
    ]
    client = make_mock_client(devices=devices)

    # Mock DeviceType.is_luba1 to identify Luba-0000 as Luba1
    with (
        patch(PATCH_CLIENT, return_value=client),
        patch(
            "custom_components.mammotion_lite.config_flow.DeviceType.is_luba1",
            side_effect=lambda name: name == "Luba-0000",
        ),
    ):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    # Should auto-create entry for the single remaining device
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_NAME] == "Luba-VSLKJX"


async def test_yuka_device_is_supported(hass: HomeAssistant, flow):
    """Yuka devices are included in the compatible device list."""
    client = make_mock_client(devices=[FakeDevice(device_name="Yuka-ABC123", iot_id="yuka1")])

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_NAME] == "Yuka-ABC123"


async def test_duplicate_device_aborts(hass: HomeAssistant, flow):
    """Configuring an already-configured device aborts."""
    client = make_mock_client(devices=[FakeDevice(device_name="Luba-VSLKJX", iot_id="abc123")])

    # First: create initial entry
    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Second: try to add same device again
    with patch(PATCH_CLIENT, return_value=client):
        result2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_client_stopped_after_login(hass: HomeAssistant, flow):
    """Client is stopped after login attempt regardless of outcome."""
    client = make_mock_client(devices=[FakeDevice(device_name="Luba-VSLKJX", iot_id="abc123")])

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    client.stop.assert_awaited_once()


async def test_client_stopped_on_failure(hass: HomeAssistant, flow):
    """Client is stopped even when login fails."""
    client = make_mock_client(login_succeeds=False)

    with patch(PATCH_CLIENT, return_value=client):
        result = await flow()
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTNAME: "user@example.com", CONF_PASSWORD: "bad"},
        )

    client.stop.assert_awaited_once()
