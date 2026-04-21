"""Config flow for Mammotion Lite integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import aiohttp_client
from pymammotion.client import MammotionClient
from pymammotion.utility.device_type import DeviceType

from .const import CONF_ACCOUNTNAME, CONF_DEVICE_IOT_ID, CONF_DEVICE_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_SUPPORT = ("Luba", "Yuka")


class MammotionLiteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mammotion Lite."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._devices: list[dict[str, str]] = []
        self._account: str = ""
        self._password: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            account = user_input[CONF_ACCOUNTNAME]
            password = user_input[CONF_PASSWORD]

            client = MammotionClient()
            session = aiohttp_client.async_get_clientsession(self.hass)

            try:
                await client.login_and_initiate_cloud(account, password, session)

                if client.mammotion_http is None or client.mammotion_http.login_info is None:
                    errors["base"] = "invalid_auth"
                else:
                    devices = [
                        *client.aliyun_device_list,
                        *client.mammotion_device_list,
                    ]
                    camera_devices = [
                        d
                        for d in devices
                        if d.device_name.startswith(DEVICE_SUPPORT)
                        and not DeviceType.is_luba1(d.device_name)
                    ]

                    if not camera_devices:
                        errors["base"] = "no_devices"
                    elif len(camera_devices) == 1:
                        device = camera_devices[0]
                        await self.async_set_unique_id(f"{account}_{device.device_name}")
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=device.device_name,
                            data={
                                CONF_ACCOUNTNAME: account,
                                CONF_PASSWORD: password,
                                CONF_DEVICE_NAME: device.device_name,
                                CONF_DEVICE_IOT_ID: device.iot_id,
                            },
                        )
                    else:
                        self._account = account
                        self._password = password
                        self._devices = [
                            {"name": d.device_name, "iot_id": d.iot_id}
                            for d in camera_devices
                        ]
                        return await self.async_step_select_device()

            except AbortFlow:
                raise
            except Exception:
                _LOGGER.exception("Failed to connect to Mammotion cloud")
                errors["base"] = "cannot_connect"
            finally:
                await client.stop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCOUNTNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device selection when multiple devices exist."""
        if user_input is not None:
            device_name = user_input[CONF_DEVICE_NAME]
            device = next(d for d in self._devices if d["name"] == device_name)

            await self.async_set_unique_id(f"{self._account}_{device_name}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=device_name,
                data={
                    CONF_ACCOUNTNAME: self._account,
                    CONF_PASSWORD: self._password,
                    CONF_DEVICE_NAME: device_name,
                    CONF_DEVICE_IOT_ID: device["iot_id"],
                },
            )

        device_names = [d["name"] for d in self._devices]
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_NAME): vol.In(device_names)}
            ),
        )
