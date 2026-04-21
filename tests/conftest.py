"""Shared test fixtures for mammotion_lite tests."""

from __future__ import annotations

import asyncio
import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from homeassistant import loader
from homeassistant.core import HomeAssistant

import threading


def _ensure_pycares_thread() -> None:
    """Start pycares daemon thread at module import time.

    pymammotion -> aiodns -> pycares lazily creates a daemon thread on first
    Channel construction. If this happens mid-test, verify_cleanup sees a
    new thread that wasn't in its 'before' snapshot and fails.
    Starting it here means it's always in the snapshot.
    """
    try:
        import pycares
        import time

        pycares.Channel()
        time.sleep(0.05)  # let the daemon thread start
    except (ImportError, Exception):
        pass


_ensure_pycares_thread()


_COMPONENT_DIR = pathlib.Path(__file__).parent.parent / "custom_components" / "mammotion_lite"

# Ensure our custom_components directory is importable even when
# pytest-homeassistant-custom-component replaces the custom_components
# namespace with its testing_config version.
_repo_root = pathlib.Path(__file__).parent.parent
import sys as _sys

if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

# Force-register our custom component package so imports resolve
import importlib
import types

_cc = _sys.modules.get("custom_components")
if _cc is not None:
    # Add our custom_components dir to the namespace package path
    _our_cc_path = str(_repo_root / "custom_components")
    if _our_cc_path not in _cc.__path__:
        _cc.__path__.insert(0, _our_cc_path)


@pytest.fixture(autouse=True)
def _register_custom_component(hass: HomeAssistant) -> None:
    """Register mammotion_lite as a custom component so the HA loader can find it."""
    manifest = json.loads((_COMPONENT_DIR / "manifest.json").read_text())
    integration = loader.Integration(
        hass,
        "custom_components.mammotion_lite",
        _COMPONENT_DIR,
        manifest,
        set(str(p.name) for p in _COMPONENT_DIR.iterdir()),
    )
    hass.data.setdefault(loader.DATA_CUSTOM_COMPONENTS, {})[
        "mammotion_lite"
    ] = integration


# ---------------------------------------------------------------------------
# Lightweight fakes for pymammotion types
# ---------------------------------------------------------------------------
# These mirror the shapes of the real pymammotion classes just enough
# to test our integration logic without importing the actual library
# (which drags in protobuf, MQTT, etc.).
# ---------------------------------------------------------------------------


@dataclass
class FakeSubscription:
    """Mimics pymammotion.transport.base.Subscription."""

    _cancelled: bool = False

    def cancel(self) -> None:
        self._cancelled = True


@dataclass
class FakePropertyValue:
    """Mimics a single property item (e.g. batteryPercentage, deviceState)."""

    value: Any = None


@dataclass
class FakePropertyItems:
    """Mimics ThingPropertiesMessage.params.items with common fields."""

    batteryPercentage: FakePropertyValue | None = None
    deviceState: FakePropertyValue | None = None
    networkInfo: FakePropertyValue | None = None
    coordinate: FakePropertyValue | None = None
    knifeHeight: FakePropertyValue | None = None


@dataclass
class FakePropertiesParams:
    """Mimics ThingPropertiesMessage.params."""

    items: FakePropertyItems = field(default_factory=FakePropertyItems)


@dataclass
class FakeThingPropertiesMessage:
    """Mimics pymammotion.data.mqtt.properties.ThingPropertiesMessage."""

    method: str = "thing.properties"
    id: str = "1"
    params: FakePropertiesParams = field(default_factory=FakePropertiesParams)
    version: str = "1.0"


class FakeStatusType:
    """Mimics pymammotion.data.mqtt.status.StatusType enum values."""

    CONNECTED = "1"
    DISCONNECTED = "0"


@dataclass
class FakeStatusValue:
    """Mimics the status value inside ThingStatusMessage.params."""

    value: str = "1"  # "1" = CONNECTED


@dataclass
class FakeStatusParams:
    """Mimics ThingStatusMessage.params."""

    status: FakeStatusValue = field(default_factory=FakeStatusValue)


@dataclass
class FakeThingStatusMessage:
    """Mimics pymammotion.data.mqtt.status.ThingStatusMessage."""

    method: str = "thing.status"
    id: str = "1"
    params: FakeStatusParams = field(default_factory=FakeStatusParams)
    version: str = "1.0"


@dataclass
class FakeEventValue:
    """Mimics the event value payload."""

    data: str = ""


@dataclass
class FakeEventParams:
    """Mimics ThingEventMessage.params for device_notification_event."""

    identifier: str = ""
    value: FakeEventValue | None = None


@dataclass
class FakeThingEventMessage:
    """Mimics pymammotion.data.mqtt.event.ThingEventMessage."""

    method: str = "thing.events"
    id: str = "1"
    params: FakeEventParams = field(default_factory=FakeEventParams)
    version: str = "1.0"


@dataclass
class FakeWorkData:
    """Mimics the work section of report data."""

    area: int = 0
    progress: int = 0


@dataclass
class FakeReportData:
    """Mimics MowerDevice.report_data."""

    work: FakeWorkData = field(default_factory=FakeWorkData)


@dataclass
class FakeRaw:
    """Mimics DeviceSnapshot.raw (MowerDevice)."""

    report_data: FakeReportData = field(default_factory=FakeReportData)


@dataclass
class FakeDeviceSnapshot:
    """Mimics pymammotion.state.device_state.DeviceSnapshot."""

    sequence: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    online: bool = True
    enabled: bool = True
    battery_level: int = 0
    mowing_activity: str = "unknown(0)"
    blade_height: int = 0
    raw: FakeRaw = field(default_factory=FakeRaw)


@dataclass
class FakeLoginUserInfo:
    """Mimics login_info.userInformation."""

    userAccount: str = "12345"


@dataclass
class FakeLoginInfo:
    """Mimics mammotion_http.login_info."""

    userInformation: FakeLoginUserInfo = field(default_factory=FakeLoginUserInfo)


@dataclass
class FakeDevice:
    """Mimics a device entry from aliyun_device_list / mammotion_device_list."""

    device_name: str = "Luba-VSLKJX"
    iot_id: str = "abc123"


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def make_properties_message(
    *,
    battery: int | None = None,
    device_state: str | None = None,
    network_info: dict | None = None,
    coordinate: dict | None = None,
    knife_height: int | None = None,
) -> FakeThingPropertiesMessage:
    """Build a FakeThingPropertiesMessage with specified fields."""
    items = FakePropertyItems(
        batteryPercentage=FakePropertyValue(battery) if battery is not None else None,
        deviceState=FakePropertyValue(device_state) if device_state is not None else None,
        networkInfo=(
            FakePropertyValue(json.dumps(network_info)) if network_info is not None else None
        ),
        coordinate=(
            FakePropertyValue(json.dumps(coordinate)) if coordinate is not None else None
        ),
        knifeHeight=FakePropertyValue(knife_height) if knife_height is not None else None,
    )
    return FakeThingPropertiesMessage(params=FakePropertiesParams(items=items))


def make_event_message(
    identifier: str = "device_notification_event",
    code: str | None = None,
    extra_data: dict | None = None,
) -> FakeThingEventMessage:
    """Build a FakeThingEventMessage with a notification code."""
    if code is not None:
        data = {"code": code}
        if extra_data:
            data.update(extra_data)
        value = FakeEventValue(data=json.dumps(data))
    else:
        value = None

    return FakeThingEventMessage(
        params=FakeEventParams(identifier=identifier, value=value)
    )


def make_status_message(*, connected: bool = True) -> FakeThingStatusMessage:
    """Build a FakeThingStatusMessage."""
    status_value = FakeStatusType.CONNECTED if connected else FakeStatusType.DISCONNECTED
    return FakeThingStatusMessage(
        params=FakeStatusParams(status=FakeStatusValue(value=status_value))
    )


def make_snapshot(
    *,
    battery_level: int = 80,
    mowing_activity: str = "mowing",
    blade_height: int = 50,
    area: int = 0,
    online: bool = True,
    sequence: int = 1,
) -> FakeDeviceSnapshot:
    """Build a FakeDeviceSnapshot."""
    return FakeDeviceSnapshot(
        sequence=sequence,
        online=online,
        battery_level=battery_level,
        mowing_activity=mowing_activity,
        blade_height=blade_height,
        raw=FakeRaw(report_data=FakeReportData(work=FakeWorkData(area=area))),
    )


def make_mock_client(
    *,
    devices: list[FakeDevice] | None = None,
    login_succeeds: bool = True,
    mower_handle: MagicMock | None = "auto",
) -> MagicMock:
    """Build a mock MammotionClient.

    Args:
        devices: List of fake devices to return from device lists.
        login_succeeds: Whether login_and_initiate_cloud succeeds.
        mower_handle: Mock for client.mower(). Pass "auto" for a default mock,
                      None for no handle, or a custom MagicMock.
    """
    client = MagicMock()

    # Login
    if login_succeeds:
        client.login_and_initiate_cloud = AsyncMock()
        client.mammotion_http = MagicMock()
        client.mammotion_http.login_info = FakeLoginInfo()
    else:
        client.login_and_initiate_cloud = AsyncMock(side_effect=Exception("Connection failed"))
        client.mammotion_http = None

    # Device lists
    if devices is None:
        devices = [FakeDevice()]
    client.aliyun_device_list = devices
    client.mammotion_device_list = []

    # Mower handle
    if mower_handle == "auto":
        handle = MagicMock()
        handle.send_raw = AsyncMock()
        handle.subscribe_state_changed = MagicMock(return_value=FakeSubscription())
        client.mower = MagicMock(return_value=handle)
    elif mower_handle is None:
        client.mower = MagicMock(return_value=None)
    else:
        client.mower = MagicMock(return_value=mower_handle)

    # Subscriptions
    client.subscribe_device_properties = MagicMock(return_value=FakeSubscription())
    client.subscribe_device_status = MagicMock(return_value=FakeSubscription())
    client.subscribe_device_event = MagicMock(return_value=FakeSubscription())
    client.setup_device_watchers = MagicMock()
    client.teardown_device_watchers = MagicMock()

    # Stop
    client.stop = AsyncMock()

    # Stream subscription
    client.get_stream_subscription = AsyncMock(return_value=None)

    return client


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> MagicMock:
    """Provide a default mock MammotionClient."""
    return make_mock_client()


@pytest.fixture
def fake_snapshot() -> FakeDeviceSnapshot:
    """Provide a default fake DeviceSnapshot."""
    return make_snapshot()


@pytest.fixture
def fake_properties() -> FakeThingPropertiesMessage:
    """Provide a default fake ThingPropertiesMessage with common data."""
    return make_properties_message(
        battery=75,
        device_state="standby",
        network_info={"wifi_rssi": -55},
        coordinate={"lat": -33.8688, "lon": 151.2093},
        knife_height=45,
    )
