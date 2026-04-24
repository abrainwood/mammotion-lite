"""Contract tests for pymammotion API surface.

These tests verify that the pymammotion classes we depend on have the
attributes and methods we expect. If pymammotion changes its API in a
new version, these tests fail BEFORE we deploy to a real mower.

Unlike our unit tests which use fakes, these import the REAL pymammotion
classes. A failure here means our fakes have diverged from reality.
"""

from __future__ import annotations

import pytest


class TestDeviceSnapshotContract:
    """Verify DeviceSnapshot has the fields we read."""

    def test_has_battery_level(self):
        """We read snapshot.battery_level for battery sensor."""
        from pymammotion.state.device_state import DeviceSnapshot
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DeviceSnapshot)}
        assert "battery_level" in fields

    def test_has_online(self):
        """We read snapshot.online for connectivity."""
        from pymammotion.state.device_state import DeviceSnapshot
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DeviceSnapshot)}
        assert "online" in fields

    def test_has_raw(self):
        """We read snapshot.raw for report_data and location."""
        from pymammotion.state.device_state import DeviceSnapshot
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DeviceSnapshot)}
        assert "raw" in fields

    def test_has_timestamp(self):
        """We compare snapshot.timestamp for battery freshness."""
        from pymammotion.state.device_state import DeviceSnapshot
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DeviceSnapshot)}
        assert "timestamp" in fields

    def test_has_sequence(self):
        """We log snapshot.sequence for debugging."""
        from pymammotion.state.device_state import DeviceSnapshot
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DeviceSnapshot)}
        assert "sequence" in fields


class TestMowingDeviceContract:
    """Verify MowingDevice (snapshot.raw) has the nested fields we read."""

    def test_report_data_dev_battery_val(self):
        """Battery from report_data.dev.battery_val."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.report_data.dev, "battery_val")

    def test_report_data_dev_sys_status(self):
        """Activity from report_data.dev.sys_status."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.report_data.dev, "sys_status")

    def test_report_data_work_area(self):
        """Job progress from report_data.work.area."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.report_data.work, "area")

    def test_report_data_work_knife_height(self):
        """Blade height from report_data.work.knife_height."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.report_data.work, "knife_height")

    def test_report_data_work_ub_zone_hash(self):
        """Zone hash from report_data.work.ub_zone_hash."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.report_data.work, "ub_zone_hash")

    def test_report_data_connect_wifi_rssi(self):
        """WiFi RSSI from report_data.connect.wifi_rssi."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.report_data.connect, "wifi_rssi")

    def test_location_device_latitude_longitude(self):
        """GPS from location.device.latitude/longitude."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.location.device, "latitude")
        assert hasattr(m.location.device, "longitude")

    def test_location_position_type(self):
        """Position quality from location.position_type."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.location, "position_type")

    def test_location_rtk(self):
        """RTK base station from location.RTK."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.location, "RTK")
        assert hasattr(m.location.RTK, "latitude")
        assert hasattr(m.location.RTK, "longitude")

    def test_map_area_name(self):
        """Area names from map.area_name."""
        from pymammotion.data.model.device import MowingDevice
        m = MowingDevice()
        assert hasattr(m.map, "area_name")
        assert isinstance(m.map.area_name, list)


class TestMammotionClientContract:
    """Verify MammotionClient has the methods we call."""

    def test_has_login_and_initiate_cloud(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "login_and_initiate_cloud")

    def test_has_setup_device_watchers(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "setup_device_watchers")

    def test_has_subscribe_device_properties(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "subscribe_device_properties")

    def test_has_subscribe_device_status(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "subscribe_device_status")

    def test_has_subscribe_device_event(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "subscribe_device_event")

    def test_has_mower(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "mower")

    def test_has_get_stream_subscription(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "get_stream_subscription")

    def test_has_get_device_by_name(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "get_device_by_name")

    def test_has_stop(self):
        from pymammotion.client import MammotionClient
        assert hasattr(MammotionClient, "stop")


class TestMammotionCommandContract:
    """Verify MammotionCommand has the methods we call."""

    def test_has_request_iot_sys(self):
        from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
        assert hasattr(MammotionCommand, "request_iot_sys")

    def test_has_device_agora_join_channel(self):
        from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
        assert hasattr(MammotionCommand, "device_agora_join_channel_with_position")

    def test_has_refresh_fpv(self):
        from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
        assert hasattr(MammotionCommand, "refresh_fpv")

    def test_has_get_area_name_list(self):
        from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
        assert hasattr(MammotionCommand, "get_area_name_list")


class TestProtoEnumsContract:
    """Verify proto enums we use exist."""

    def test_rpt_act(self):
        from pymammotion.proto import RptAct
        assert hasattr(RptAct, "RPT_START")
        assert hasattr(RptAct, "RPT_STOP")

    def test_rpt_info_type(self):
        from pymammotion.proto import RptInfoType
        assert hasattr(RptInfoType, "RIT_DEV_STA")
        assert hasattr(RptInfoType, "RIT_WORK")
        assert hasattr(RptInfoType, "RIT_DEV_LOCAL")
        assert hasattr(RptInfoType, "RIT_CONNECT")
        assert hasattr(RptInfoType, "RIT_RTK")


class TestMqttMessageContract:
    """Verify MQTT message types we depend on exist and have expected shape."""

    def test_thing_properties_message_importable(self):
        from pymammotion.data.mqtt.properties import ThingPropertiesMessage
        assert ThingPropertiesMessage is not None

    def test_thing_status_message_importable(self):
        from pymammotion.data.mqtt.status import ThingStatusMessage, StatusType
        assert hasattr(StatusType, "CONNECTED")
        assert hasattr(StatusType, "DISCONNECTED")

    def test_thing_event_message_importable(self):
        from pymammotion.data.mqtt.event import ThingEventMessage
        assert ThingEventMessage is not None

    def test_subscription_importable(self):
        from pymammotion.transport.base import Subscription
        assert Subscription is not None
