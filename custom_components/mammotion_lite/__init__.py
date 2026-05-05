"""Mammotion Lite - lightweight mower integration with passive sensors + on-demand camera."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from pymammotion.client import MammotionClient
from pymammotion.data.mqtt.status import StatusType
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import RptAct, RptInfoType
from pymammotion.transport.base import LoginFailedError

from .const import (
    CONF_ACCOUNTNAME,
    CONF_DEVICE_IOT_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
    EVENT_CODE_LABELS,
    START_REPORTING_CODES,
    STOP_REPORTING_CODES,
)
from .event_handling import extract_event_code, get_event_label
from .runtime_data import MammotionLiteData

_LOGGER = logging.getLogger(__name__)

# RPT_START config
_REPORT_PERIOD_MS = 60_000
_REPORT_TIMEOUT_MS = 180_000
_REPORT_NO_CHANGE_PERIOD_MS = 120_000
_KEEPALIVE_INTERVAL_S = 120

# Map sync retry backoff delays in seconds (after the initial attempt)
_MAP_SYNC_BACKOFF_S = (60, 120, 300)

PLATFORMS = [
    Platform.CAMERA,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
]

type MammotionLiteConfigEntry = ConfigEntry[MammotionLiteData]


async def _send_rpt_start(data: MammotionLiteData) -> None:
    """Send RPT_START command to begin/renew 60-second reporting."""
    handle = data.client.mower(data.device_name)
    if handle is None:
        _LOGGER.warning("RPT_START: no mower handle for %s", data.device_name)
        return
    try:
        command = data.commands.request_iot_sys(
            rpt_act=RptAct.RPT_START,
            rpt_info_type=[
                RptInfoType.RIT_DEV_STA,
                RptInfoType.RIT_WORK,
                RptInfoType.RIT_DEV_LOCAL,
                RptInfoType.RIT_CONNECT,
                RptInfoType.RIT_RTK,
            ],
            timeout=_REPORT_TIMEOUT_MS,
            period=_REPORT_PERIOD_MS,
            no_change_period=_REPORT_NO_CHANGE_PERIOD_MS,
            count=0,
        )
        await handle.send_raw(command)
        data.reporting_active = True
        data.last_report_time = time.monotonic()
        _LOGGER.debug("RPT_START sent for %s", data.device_name)
    except Exception:
        _LOGGER.warning("RPT_START failed for %s", data.device_name, exc_info=True)


async def _send_rpt_stop(data: MammotionLiteData) -> None:
    """Send RPT_STOP command to cease reporting."""
    handle = data.client.mower(data.device_name)
    if handle is None:
        return
    try:
        command = data.commands.request_iot_sys(
            rpt_act=RptAct.RPT_STOP,
            rpt_info_type=[],
            timeout=0,
            period=0,
            no_change_period=0,
            count=0,
        )
        await handle.send_raw(command)
        data.reporting_active = False
        _LOGGER.debug("RPT_STOP sent for %s", data.device_name)
    except Exception:
        _LOGGER.warning("RPT_STOP failed for %s", data.device_name, exc_info=True)


async def _keepalive_loop(data: MammotionLiteData) -> None:
    """Re-send RPT_START every 2 minutes while mower is working."""
    _LOGGER.debug("Keepalive loop started for %s", data.device_name)
    try:
        while True:
            await asyncio.sleep(_KEEPALIVE_INTERVAL_S)
            if not data.reporting_active:
                continue
            _LOGGER.debug("Keepalive: renewing RPT_START for %s", data.device_name)
            await _send_rpt_start(data)
    except asyncio.CancelledError:
        _LOGGER.debug("Keepalive loop cancelled for %s", data.device_name)


def _start_keepalive(data: MammotionLiteData) -> None:
    """Start the keepalive loop if not already running."""
    if data._keepalive_task is None or data._keepalive_task.done():
        data._keepalive_task = asyncio.ensure_future(_keepalive_loop(data))


def _stop_keepalive(data: MammotionLiteData) -> None:
    """Cancel the keepalive loop."""
    if data._keepalive_task and not data._keepalive_task.done():
        data._keepalive_task.cancel()
        data._keepalive_task = None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Mammotion Lite component - register static files."""
    from pathlib import Path

    from homeassistant.components.http import StaticPathConfig

    www_path = Path(__file__).parent / "www"
    if www_path.exists() and hass.http is not None:
        js_file = www_path / "agora-client.js"
        if js_file.exists():
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        "/mammotion_lite/agora-client.js",
                        str(js_file),
                        True,
                    )
                ]
            )
    return True


async def _load_area_names(data: MammotionLiteData, device_name: str) -> None:
    """Load area names via map sync with retry on failure.

    The saga's first step fetches user-defined names via broker.send_and_wait.
    Later steps download boundary data whose hashes we use for fallback names.
    area_name is volatile (saga retries can overwrite it), so we capture
    entries into our own dict as they appear.

    Retries with backoff if the saga fails (e.g. MQTT not ready at startup).
    """
    # Cloud transports need a longer saga timeout than the 3s default.
    # TODO: remove once pymammotion ships transport-aware timeouts
    # (see abrainwood/PyMammotion branch transport-aware-saga-timeout)
    from pymammotion.messaging.map_saga import MapFetchSaga

    MapFetchSaga.step_timeout = 15.0

    max_attempts = 1 + len(_MAP_SYNC_BACKOFF_S)
    for attempt in range(max_attempts):
        try:
            await data.client.start_map_sync(data.device_name)
            _LOGGER.debug(
                "Map sync enqueued for %s (attempt %d/%d)",
                device_name, attempt + 1, max_attempts,
            )
            named: dict[int, str] = {}
            area_hashes: set[int] = set()
            for _ in range(180):
                await asyncio.sleep(1)
                device = data.client.get_device_by_name(data.device_name)
                if not device:
                    continue
                for a in device.map.area_name:
                    if a.hash not in named:
                        named[a.hash] = a.name
                area_hashes.update(getattr(device.map, "area", {}).keys())
            # Merge: user names + fallbacks for unnamed areas
            unnamed = sorted(area_hashes - set(named.keys()))
            fallback_n = 1
            merged = dict(named)
            for h in unnamed:
                merged[h] = f"Area {fallback_n}"
                fallback_n += 1
            if merged:
                data.area_names = merged
                _LOGGER.info(
                    "[AREA] %s: area_name hashes=%s, map.area keys=%s, merged=%s",
                    device_name,
                    {a.hash: a.name for a in device.map.area_name} if device else {},
                    list(area_hashes),
                    data.area_names,
                )
                data.create_area_sensors()
                return
            _LOGGER.warning(
                "No area data received for %s (attempt %d/%d)",
                device_name, attempt + 1, max_attempts,
            )
        except Exception:
            _LOGGER.warning(
                "Map sync failed for %s (attempt %d/%d)",
                device_name, attempt + 1, max_attempts, exc_info=True,
            )

        if attempt < len(_MAP_SYNC_BACKOFF_S):
            delay = _MAP_SYNC_BACKOFF_S[attempt]
            _LOGGER.info("Retrying map sync for %s in %ds", device_name, delay)
            await asyncio.sleep(delay)

    _LOGGER.warning(
        "Map sync exhausted all retries for %s - area sensors unavailable until restart",
        device_name,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: MammotionLiteConfigEntry
) -> bool:
    """Set up Mammotion Lite from a config entry."""
    account = entry.data[CONF_ACCOUNTNAME]
    password = entry.data[CONF_PASSWORD]
    device_name = entry.data[CONF_DEVICE_NAME]
    iot_id = entry.data[CONF_DEVICE_IOT_ID]

    _LOGGER.debug("async_setup_entry: device=%s", device_name)

    client = MammotionClient()
    session = aiohttp_client.async_get_clientsession(hass)

    try:
        await client.login_and_initiate_cloud(account, password, session)
    except LoginFailedError as err:
        _LOGGER.error(
            "Mammotion cloud auth failed for %s: %s", device_name, err.reason,
        )
        # Auth failures don't self-heal - retrying could lock the account further
        data = MammotionLiteData(
            client=client,
            commands=MammotionCommand(device_name, user_account=0),
            device_name=device_name,
            iot_id=iot_id,
        )
        entry.runtime_data = data
        return True
    except Exception:
        _LOGGER.warning(
            "Failed to connect to Mammotion cloud for %s - will retry", device_name,
            exc_info=True,
        )
        # Graceful degradation: create data with no subscriptions, retry later
        data = MammotionLiteData(
            client=client,
            commands=MammotionCommand(device_name, user_account=0),
            device_name=device_name,
            iot_id=iot_id,
        )
        entry.runtime_data = data
        _schedule_cloud_retry(hass, entry)
        return True

    if client.mammotion_http is None or client.mammotion_http.login_info is None:
        _LOGGER.warning("Login succeeded but no session data for %s - will retry", device_name)
        data = MammotionLiteData(
            client=client,
            commands=MammotionCommand(device_name, user_account=0),
            device_name=device_name,
            iot_id=iot_id,
        )
        entry.runtime_data = data
        _schedule_cloud_retry(hass, entry)
        return True

    try:
        user_account = int(client.mammotion_http.login_info.userInformation.userAccount)
    except (ValueError, TypeError):
        _LOGGER.warning("Could not parse user_account as int, using 0")
        user_account = 0
    commands = MammotionCommand(device_name, user_account=user_account)

    data = MammotionLiteData(
        client=client,
        commands=commands,
        device_name=device_name,
        iot_id=iot_id,
    )
    entry.runtime_data = data

    _setup_subscriptions(data, client, device_name)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Initial state probe (self-expires after 30s)
    async def _initial_probe() -> None:
        await asyncio.sleep(10)

        # Probe needs a mower handle but map sync does not - keep them independent
        probe_handle = data.client.mower(data.device_name)
        if probe_handle is not None:
            try:
                command = data.commands.request_iot_sys(
                    rpt_act=RptAct.RPT_START,
                    rpt_info_type=[
                        RptInfoType.RIT_DEV_STA,
                        RptInfoType.RIT_WORK,
                        RptInfoType.RIT_DEV_LOCAL,
                        RptInfoType.RIT_CONNECT,
                    ],
                    timeout=30_000,
                    period=10_000,
                    no_change_period=30_000,
                    count=3,
                )
                await probe_handle.send_raw(command)
                _LOGGER.debug("Initial probe sent for %s", device_name)
            except Exception:
                _LOGGER.debug("Initial probe failed for %s", device_name)
        else:
            _LOGGER.debug("Initial probe: no mower handle for %s", device_name)

        await _load_area_names(data, device_name)

    entry.async_create_background_task(
        hass, _initial_probe(), f"mammotion_lite_probe_{device_name}"
    )

    return True


def _log_event_code(device_name: str, code: str) -> None:
    """Log event code at appropriate level."""
    if code in EVENT_CODE_LABELS:
        _LOGGER.debug("[EVENT] %s: code=%s (%s)", device_name, code, EVENT_CODE_LABELS[code])
    else:
        _LOGGER.warning("[EVENT] %s: unknown event code %s - please report this", device_name, code)


async def _handle_rpt_trigger(data: MammotionLiteData, code: str) -> None:
    """Start or stop reporting based on event code."""
    if code in START_REPORTING_CODES:
        _LOGGER.debug("Event %s -> starting reporting", code)
        await _send_rpt_start(data)
        _start_keepalive(data)
    elif code in STOP_REPORTING_CODES:
        _LOGGER.debug("Event %s -> stopping reporting", code)
        await _send_rpt_stop(data)
        _stop_keepalive(data)


def _setup_subscriptions(
    data: MammotionLiteData, client: MammotionClient, device_name: str
) -> None:
    """Wire up MQTT push subscriptions."""
    client.setup_device_watchers(device_name)

    async def _on_properties(props) -> None:
        _LOGGER.debug("[PROPS] %s received", device_name)
        data.properties = props
        data.dispatch_sensor_update()

    async def _on_status(status) -> None:
        is_online = status.params.status.value == StatusType.CONNECTED
        _LOGGER.debug("[STATUS] %s: online=%s", device_name, is_online)
        data.online = is_online
        data.dispatch_update()

    async def _on_state_changed(snapshot) -> None:
        _LOGGER.debug("[STATE] %s: battery=%d", device_name, snapshot.battery_level)
        data.snapshot = snapshot
        data.online = snapshot.online
        data.last_report_time = time.monotonic()

        # Capture current zone from device.location.work_zone (matches area_names keys)
        try:
            device = client.get_device_by_name(device_name)
            if device and device.location:
                data.current_zone_hash = device.location.work_zone
        except AttributeError:
            _LOGGER.debug("No location.work_zone available for %s", device_name)

        # Detect mow completion: progress drops from >=90% to 0
        from .sensors import get_progress, get_zone_hash

        progress = get_progress(data) or 0

        # Store zone hashes while mowing (snapshot clears them at completion)
        if progress > 0:
            try:
                work_zones = snapshot.raw.work.zone_hashs
                if work_zones:
                    # Filter out zeros and store the active zones
                    active = [z for z in work_zones if z != 0]
                    if active:
                        data.active_zone_hashs = active
                    _LOGGER.debug(
                        "[WORK] %s: progress=%d%%, zone_hashs=%s, ub_zone_hash=%s",
                        device_name, progress, work_zones,
                        snapshot.raw.report_data.work.ub_zone_hash,
                    )
            except AttributeError:
                pass

        if data.last_progress >= 90 and progress == 0:
            # Use stored zone_hashs (snapshot clears them at completion)
            task_zones = data.active_zone_hashs.copy()
            # Fall back to single zone hash
            if not task_zones:
                zone_hash = get_zone_hash(data)
                if zone_hash:
                    task_zones = [zone_hash]
            for zh in task_zones:
                if zh in data.area_names:
                    data.mow_history[zh] = datetime.now(timezone.utc)
                    _LOGGER.info(
                        "Mow completed in %s for %s",
                        data.area_names[zh], device_name,
                    )
            # Clear stored zones after recording
            data.active_zone_hashs = []
        data.last_progress = progress

        data.dispatch_sensor_update()

    async def _on_event(event) -> None:
        code = extract_event_code(event)
        if not code:
            identifier = getattr(event.params, "identifier", None)
            _LOGGER.debug("[EVENT] %s: identifier=%s (no code)", device_name, identifier)
            return

        _log_event_code(device_name, code)
        data.last_event_code = code
        data.last_event_label = get_event_label(code)
        data.last_event_time = datetime.now(timezone.utc)

        data.dispatch_update()
        await _handle_rpt_trigger(data, code)

    sub_props = client.subscribe_device_properties(device_name, _on_properties)
    if sub_props:
        data._subscriptions.append(sub_props)

    sub_status = client.subscribe_device_status(device_name, _on_status)
    if sub_status:
        data._subscriptions.append(sub_status)

    sub_event = client.subscribe_device_event(device_name, _on_event)
    if sub_event:
        data._subscriptions.append(sub_event)

    handle = client.mower(device_name)
    if handle is not None:
        sub_state = handle.subscribe_state_changed(_on_state_changed)
        if sub_state:
            data._subscriptions.append(sub_state)
    else:
        _LOGGER.warning("No mower handle for %s - state_changed skipped", device_name)


def _schedule_cloud_retry(hass: HomeAssistant, entry: MammotionLiteConfigEntry) -> None:
    """Schedule a background retry for cloud connection."""
    device_name = entry.data[CONF_DEVICE_NAME]
    entry.async_create_background_task(
        hass, _cloud_retry(hass, entry), f"mammotion_lite_cloud_retry_{device_name}"
    )


async def _cloud_retry(hass: HomeAssistant, entry: MammotionLiteConfigEntry) -> None:
    """Retry cloud connection after a delay."""
    await asyncio.sleep(60)
    device_name = entry.data[CONF_DEVICE_NAME]
    _LOGGER.debug("Cloud retry for %s", device_name)
    try:
        data = entry.runtime_data
        session = aiohttp_client.async_get_clientsession(hass)
        await data.client.login_and_initiate_cloud(
            entry.data[CONF_ACCOUNTNAME],
            entry.data[CONF_PASSWORD],
            session,
        )
        if data.client.mammotion_http and data.client.mammotion_http.login_info:
            try:
                user_account = int(
                    data.client.mammotion_http.login_info.userInformation.userAccount
                )
            except (ValueError, TypeError):
                _LOGGER.warning("Could not parse user_account as int during retry, using 0")
                user_account = 0
            data.commands = MammotionCommand(data.device_name, user_account=user_account)
            _setup_subscriptions(data, data.client, data.device_name)
            _LOGGER.info("Cloud retry succeeded for %s", device_name)
        else:
            _LOGGER.warning("Cloud retry: no session data for %s", device_name)
    except Exception:
        _LOGGER.warning("Cloud retry failed for %s", device_name, exc_info=True)


async def async_unload_entry(
    hass: HomeAssistant, entry: MammotionLiteConfigEntry
) -> bool:
    """Unload a config entry."""
    data = entry.runtime_data

    _stop_keepalive(data)

    if data.reporting_active:
        await _send_rpt_stop(data)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        for sub in data._subscriptions:
            sub.cancel()
        data._subscriptions.clear()

        try:
            data.client.teardown_device_watchers(data.device_name)
        except Exception:
            _LOGGER.warning("Error tearing down device watchers for %s", data.device_name)

        try:
            await data.client.stop()
        except Exception:
            _LOGGER.warning("Error stopping client during unload for %s", data.device_name)
    return unload_ok
