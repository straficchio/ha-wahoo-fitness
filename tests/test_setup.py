"""End-to-end setup tests with a fake BLE client."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wahoo_fitness.const import (
    CONF_MODEL,
    CONF_NAME,
    DOMAIN,
    MODEL_HEADWIND,
    MODEL_KICKR_BIKE,
)
from custom_components.wahoo_fitness.protocol import (
    DEVICE_NAME_UUID,
    FIRMWARE_REVISION_UUID,
    FTMS_CONTROL_POINT_UUID,
    FTMS_INDOOR_BIKE_DATA_UUID,
    FTMS_TRAINING_STATUS_UUID,
    HARDWARE_REVISION_UUID,
    HEADWIND_CONTROL_UUID,
    KICKR_GEAR_STATE_UUID,
    KICKR_SHIFTER_BUTTON_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
    SERIAL_NUMBER_UUID,
)


class FakeCharacteristic:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid


class FakeBleakClient:
    """Minimal BleakClient replacement."""

    instances: list[FakeBleakClient] = []

    def __init__(self, device: Any, **kwargs: Any) -> None:
        self.device = device
        self.is_connected = False
        self._notify: dict[str, Any] = {}
        self.writes: list[tuple[str, bytes, bool]] = []
        self._disconnected_callback = kwargs.get("disconnected_callback")
        self.instances.append(self)

    async def connect(self, **kwargs: Any) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False
        if self._disconnected_callback:
            self._disconnected_callback(self)

    async def read_gatt_char(self, uuid: str) -> bytes:
        return {
            MANUFACTURER_NAME_UUID: b"Wahoo Fitness",
            MODEL_NUMBER_UUID: b"KICKR BIKE",
            SERIAL_NUMBER_UUID: b"123456789",
            FIRMWARE_REVISION_UUID: b"1.27.0",
            HARDWARE_REVISION_UUID: b"4",
            DEVICE_NAME_UUID: b"KICKR BIKE ABCD",
        }.get(uuid, b"")

    async def start_notify(self, uuid: str, callback: Any) -> None:
        self._notify[uuid.lower()] = callback

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        payload = bytes(data)
        self.writes.append((uuid.lower(), payload, response))
        if uuid.lower() == FTMS_CONTROL_POINT_UUID and payload:
            callback = self._notify.get(FTMS_CONTROL_POINT_UUID)
            if callback:
                callback(
                    FakeCharacteristic(FTMS_CONTROL_POINT_UUID),
                    bytearray((0x80, payload[0], 0x01)),
                )

    def notify(self, uuid: str, data: bytes) -> None:
        callback = self._notify.get(uuid.lower())
        if callback:
            callback(FakeCharacteristic(uuid), bytearray(data))


async def _fake_establish(client_class: Any, device: Any, name: str, **kwargs: Any) -> Any:
    client = client_class(device, disconnected_callback=kwargs.get("disconnected_callback"))
    await client.connect()
    return client


def _entry(model: str, name: str, address: str, unique_id: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=unique_id,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: name,
            CONF_MODEL: model,
        },
    )


async def _setup(hass, entry: MockConfigEntry) -> FakeBleakClient:
    FakeBleakClient.instances.clear()
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.wahoo_fitness.coordinator.establish_connection",
            new=_fake_establish,
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.BleakClient",
            FakeBleakClient,
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.async_ble_device_from_address",
            return_value=SimpleNamespace(address=entry.data[CONF_ADDRESS]),
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()

    assert FakeBleakClient.instances, "BleakClient was not created"
    return FakeBleakClient.instances[0]


async def test_kickr_bike_entities_and_controls(hass) -> None:
    """KICKR BIKE sensors and controls use the decoded protocol."""
    entry = _entry(
        MODEL_KICKR_BIKE,
        "KICKR BIKE ABCD",
        "AA:BB:CC:DD:EE:FF",
        "kickr_bike:KICKR BIKE ABCD",
    )
    client = await _setup(hass, entry)

    # 25.00 km/h, 90 rpm, 200 W
    client.notify(FTMS_INDOOR_BIKE_DATA_UUID, bytes.fromhex("44 00 c4 09 b4 00 c8 00"))
    client.notify(KICKR_GEAR_STATE_UUID, bytes.fromhex("07 00 00 02 02 0c 00 00 00 00 00"))
    client.notify(FTMS_TRAINING_STATUS_UUID, bytes.fromhex("00 01"))
    await asyncio.sleep(1.1)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.kickr_bike_abcd_power").state == "200"
    assert hass.states.get("sensor.kickr_bike_abcd_cadence").state == "90.0"
    assert hass.states.get("sensor.kickr_bike_abcd_speed").state == "25.0"
    assert hass.states.get("sensor.kickr_bike_abcd_front_gear").state == "1"
    assert hass.states.get("sensor.kickr_bike_abcd_rear_gear").state == "3"
    assert hass.states.get("sensor.kickr_bike_abcd_front_gear_count").state == "2"
    assert hass.states.get("sensor.kickr_bike_abcd_rear_gear_count").state == "12"
    assert hass.states.get("sensor.kickr_bike_abcd_training_status").state == "idle"
    assert hass.states.get("binary_sensor.kickr_bike_abcd_connected").state == "on"
    assert hass.states.get("binary_sensor.kickr_bike_abcd_pedaling").state == "on"

    client.notify(KICKR_SHIFTER_BUTTON_UUID, bytes.fromhex("02 00 80"))
    await hass.async_block_till_done()
    left_up = hass.states.get("binary_sensor.kickr_bike_abcd_left_up")
    assert left_up.state == "on"
    assert left_up.attributes["button_id"] == "0200"
    client.notify(KICKR_SHIFTER_BUTTON_UUID, bytes.fromhex("02 00 01"))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.kickr_bike_abcd_left_up").state == "off"

    client.notify(KICKR_SHIFTER_BUTTON_UUID, bytes.fromhex("00 01 e6"))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.kickr_bike_abcd_right_up").state == "on"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.kickr_bike_abcd_target_power", "value": 150},
        blocking=True,
    )
    assert (FTMS_CONTROL_POINT_UUID, bytes.fromhex("07"), True) in client.writes
    assert (FTMS_CONTROL_POINT_UUID, bytes.fromhex("05 96 00"), True) in client.writes
    assert hass.states.get("number.kickr_bike_abcd_target_power").state == "150.0"
    assert hass.states.get("select.kickr_bike_abcd_control_mode").state == "ERG (target power)"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.kickr_bike_abcd_grade", "value": 5},
        blocking=True,
    )
    assert (
        FTMS_CONTROL_POINT_UUID,
        bytes.fromhex("11 00 00 f4 01 28 33"),
        True,
    ) in client.writes
    assert hass.states.get("number.kickr_bike_abcd_grade").state == "5.0"
    assert hass.states.get("select.kickr_bike_abcd_control_mode").state == "Simulation (grade)"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.kickr_bike_abcd_control_mode", "option": "Off"},
        blocking=True,
    )
    assert (FTMS_CONTROL_POINT_UUID, bytes.fromhex("08 01"), True) in client.writes
    assert hass.states.get("select.kickr_bike_abcd_control_mode").state == "Off"

    # A ride update includes distance accumulation.
    client.notify(FTMS_INDOOR_BIKE_DATA_UUID, bytes.fromhex("44 00 c4 09 b4 00 c8 00"))
    await asyncio.sleep(1.1)
    await hass.async_block_till_done()
    distance = hass.states.get("sensor.kickr_bike_abcd_session_distance")
    assert distance is not None
    assert float(distance.state) >= 0

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_headwind_fan_control(hass) -> None:
    """HEADWIND state and commands round-trip."""
    entry = _entry(
        MODEL_HEADWIND,
        "HEADWIND 1234",
        "11:22:33:44:55:66",
        "headwind:HEADWIND 1234",
    )
    client = await _setup(hass, entry)

    client.notify(HEADWIND_CONTROL_UUID, bytes.fromhex("fd 01 19 04"))
    await asyncio.sleep(1.1)
    await hass.async_block_till_done()

    assert hass.states.get("fan.headwind_1234").state == "on"
    assert hass.states.get("fan.headwind_1234").attributes["percentage"] == 25
    assert hass.states.get("sensor.headwind_1234_mode").state == "manual"
    assert hass.states.get("select.headwind_1234_fan_mode").state == "Manual"
    assert hass.states.get("number.headwind_1234_manual_speed").state == "25.0"

    await hass.services.async_call(
        "fan",
        "turn_on",
        {"entity_id": "fan.headwind_1234", "percentage": 60},
        blocking=True,
    )
    assert (HEADWIND_CONTROL_UUID, bytes.fromhex("04 04 00 00"), False) in client.writes
    assert (HEADWIND_CONTROL_UUID, bytes.fromhex("02 3c 00 00"), False) in client.writes
    assert hass.states.get("fan.headwind_1234").attributes["percentage"] == 60

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.headwind_1234_fan_mode", "option": "Heart rate"},
        blocking=True,
    )
    assert (HEADWIND_CONTROL_UUID, bytes.fromhex("04 02 00 00"), False) in client.writes
    assert hass.states.get("select.headwind_1234_fan_mode").state == "Heart rate"
    assert hass.states.get("sensor.headwind_1234_mode").state == "heart_rate"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.headwind_1234_manual_speed", "value": 45},
        blocking=True,
    )
    assert (HEADWIND_CONTROL_UUID, bytes.fromhex("04 04 00 00"), False) in client.writes
    assert (HEADWIND_CONTROL_UUID, bytes.fromhex("02 2d 00 00"), False) in client.writes
    assert hass.states.get("number.headwind_1234_manual_speed").state == "45.0"
    assert hass.states.get("select.headwind_1234_fan_mode").state == "Manual"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.headwind_1234_fan_mode", "option": "Speed"},
        blocking=True,
    )
    assert (HEADWIND_CONTROL_UUID, bytes.fromhex("04 03 00 00"), False) in client.writes
    assert hass.states.get("sensor.headwind_1234_mode").state == "speed"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.headwind_1234_fan_mode", "option": "Off"},
        blocking=True,
    )
    assert (HEADWIND_CONTROL_UUID, bytes.fromhex("04 01 00 00"), False) in client.writes
    assert hass.states.get("fan.headwind_1234").state == "off"
    assert hass.states.get("select.headwind_1234_fan_mode").state == "Off"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
