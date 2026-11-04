"""Wahoo Fitness BLE protocol helpers.

The KICKR BIKE exposes standard FTMS (0x1826) and Cycling Power (0x1818)
services, plus a proprietary gear-state notification.  The HEADWIND exposes
a single proprietary control characteristic.

Only pure parsing/packing lives here so it can be tested without Home
Assistant or Bluetooth.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# UUIDs
# ---------------------------------------------------------------------------

FTMS_SERVICE_UUID = "00001826-0000-1000-8000-00805f9b34fb"
FTMS_INDOOR_BIKE_DATA_UUID = "00002ad2-0000-1000-8000-00805f9b34fb"
FTMS_CONTROL_POINT_UUID = "00002ad9-0000-1000-8000-00805f9b34fb"
FTMS_STATUS_UUID = "00002ada-0000-1000-8000-00805f9b34fb"
FTMS_TRAINING_STATUS_UUID = "00002ad3-0000-1000-8000-00805f9b34fb"

CPS_SERVICE_UUID = "00001818-0000-1000-8000-00805f9b34fb"
CPS_MEASUREMENT_UUID = "00002a63-0000-1000-8000-00805f9b34fb"

DEVICE_INFO_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_NAME_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
HARDWARE_REVISION_UUID = "00002a27-0000-1000-8000-00805f9b34fb"
DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"

# KICKR BIKE proprietary service (a026ee0d)
#   0xE039 WAHOO_BIKE_CP            write/notify control point
#   0xE03A WAHOO_BIKE_STATUS        notify gear state
#   0xE03B WAHOO_SENSOR_DIAG        notify diagnostics
#   0xE03C WAHOO_BIKE_SHIFTER_BUTTON notify shifter button events
KICKR_GEAR_SERVICE_UUID = "a026ee0d-0a7d-4ab3-97fa-f1500f9feb8b"
WAHOO_BIKE_CP_UUID = "a026e039-0a7d-4ab3-97fa-f1500f9feb8b"
KICKR_GEAR_STATE_UUID = "a026e03a-0a7d-4ab3-97fa-f1500f9feb8b"
KICKR_SENSOR_DIAG_UUID = "a026e03b-0a7d-4ab3-97fa-f1500f9feb8b"
KICKR_SHIFTER_BUTTON_UUID = "a026e03c-0a7d-4ab3-97fa-f1500f9feb8b"

# HEADWIND proprietary control characteristic
HEADWIND_SERVICE_UUID = "a026ee0c-0a7d-4ab3-97fa-f1500f9feb8b"
HEADWIND_CONTROL_UUID = "a026e038-0a7d-4ab3-97fa-f1500f9feb8b"

# ---------------------------------------------------------------------------
# FTMS
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FtmsControlResponse:
    """Decoded FTMS control-point indication."""

    opcode: int
    result: int

    @property
    def success(self) -> bool:
        return self.result == 0x01

    @property
    def description(self) -> str:
        return {
            0x01: "success",
            0x02: "not supported",
            0x03: "invalid parameter",
            0x04: "operation failed",
            0x05: "control not permitted",
        }.get(self.result, f"unknown result 0x{self.result:02x}")


def parse_ftms_control_response(data: bytes) -> FtmsControlResponse | None:
    """Parse an FTMS control-point response."""
    if len(data) < 3 or data[0] != 0x80:
        return None
    return FtmsControlResponse(opcode=data[1], result=data[2])


def _need(data: bytes, offset: int, size: int) -> None:
    if offset + size > len(data):
        raise ValueError(f"short FTMS payload: need {size} bytes at offset {offset}")


def parse_indoor_bike_data(data: bytes) -> dict[str, Any]:
    """Decode an FTMS Indoor Bike Data notification.

    Fields are only included when their flag bit is set, so consumers must use
    ``.get()`` rather than assuming a fixed layout.
    """
    _need(data, 0, 2)
    flags = int.from_bytes(data[0:2], "little")
    offset = 2
    out: dict[str, Any] = {"flags": flags}

    # Bit 0 is inverted: speed is present when the bit is clear.
    if not flags & 0x0001:
        _need(data, offset, 2)
        out["speed_kmh"] = int.from_bytes(data[offset : offset + 2], "little") / 100
        offset += 2
    if flags & 0x0002:
        _need(data, offset, 2)
        out["average_speed_kmh"] = int.from_bytes(data[offset : offset + 2], "little") / 100
        offset += 2
    if flags & 0x0004:
        _need(data, offset, 2)
        out["cadence_rpm"] = int.from_bytes(data[offset : offset + 2], "little") / 2
        offset += 2
    if flags & 0x0008:
        _need(data, offset, 2)
        out["average_cadence_rpm"] = int.from_bytes(data[offset : offset + 2], "little") / 2
        offset += 2
    if flags & 0x0010:
        _need(data, offset, 3)
        out["distance_m"] = int.from_bytes(data[offset : offset + 3], "little")
        offset += 3
    if flags & 0x0020:
        _need(data, offset, 2)
        out["resistance_level"] = int.from_bytes(data[offset : offset + 2], "little") / 10
        offset += 2
    if flags & 0x0040:
        _need(data, offset, 2)
        out["power_w"] = int.from_bytes(data[offset : offset + 2], "little", signed=True)
        offset += 2
    if flags & 0x0080:
        _need(data, offset, 2)
        out["average_power_w"] = int.from_bytes(data[offset : offset + 2], "little", signed=True)
        offset += 2
    if flags & 0x0100:
        _need(data, offset, 2)
        out["total_energy_kcal"] = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2
    if flags & 0x0200:
        _need(data, offset, 2)
        out["energy_per_hour_kcal"] = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2
    if flags & 0x0400:
        _need(data, offset, 2)
        out["energy_per_minute_kcal"] = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2
    if flags & 0x0800:
        _need(data, offset, 1)
        out["heart_rate_bpm"] = data[offset]
        offset += 1
    if flags & 0x1000:
        _need(data, offset, 1)
        out["metabolic_equivalent"] = data[offset] / 10
        offset += 1
    if flags & 0x2000:
        _need(data, offset, 2)
        out["elapsed_time_s"] = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2
    if flags & 0x4000:
        _need(data, offset, 2)
        out["remaining_time_s"] = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2
    return out


def parse_cps_measurement(data: bytes) -> dict[str, Any]:
    """Decode a Cycling Power Measurement notification."""
    _need(data, 0, 4)
    flags = int.from_bytes(data[0:2], "little")
    out: dict[str, Any] = {
        "flags": flags,
        "power_w": int.from_bytes(data[2:4], "little", signed=True),
    }
    offset = 4
    if flags & 0x0001:
        _need(data, offset, 1)
        out["pedal_balance_pct"] = data[offset] / 2
        offset += 1
    if flags & 0x0004:
        _need(data, offset, 2)
        out["accumulated_torque_nm"] = int.from_bytes(data[offset : offset + 2], "little") / 32
        offset += 2
    if flags & 0x0010:
        _need(data, offset, 6)
        out["wheel_revolutions"] = int.from_bytes(data[offset : offset + 4], "little")
        out["wheel_event_time_s"] = int.from_bytes(data[offset + 4 : offset + 6], "little") / 1024
        offset += 6
    if flags & 0x0020:
        _need(data, offset, 4)
        out["crank_revolutions"] = int.from_bytes(data[offset : offset + 2], "little")
        out["crank_event_time_s"] = int.from_bytes(data[offset + 2 : offset + 4], "little") / 1024
        offset += 4
    return out


def parse_gear_state(data: bytes) -> dict[str, int]:
    """Decode the KICKR BIKE gear-state notification.

    Byte layout (0-based, confirmed against a KICKR BIKE):
      2: selected front gear (0-based)
      3: selected rear gear (0-based)
      4: number of front gears
      5: number of rear gears
    """
    if len(data) < 6:
        raise ValueError("short gear-state payload")
    return {
        "front_gear_index": data[2],
        "rear_gear_index": data[3],
        "front_gear_count": data[4],
        "rear_gear_count": data[5],
    }


TRAINING_STATUS: dict[int, str] = {
    0x00: "other",
    0x01: "idle",
    0x02: "warming_up",
    0x03: "low_intensity",
    0x04: "high_intensity",
    0x05: "recovery",
    0x06: "isometric",
    0x07: "heart_rate_control",
    0x08: "fitness_test",
    0x09: "speed_control",
    0x0A: "cool_down",
    0x0B: "watt_control",
    0x0C: "manual_mode",
    0x0D: "pre_workout",
    0x0E: "post_workout",
}


def parse_training_status(data: bytes) -> dict[str, Any]:
    """Decode FTMS Training Status."""
    if len(data) < 2:
        raise ValueError("short training-status payload")
    status = data[1]
    return {
        "training_status_flags": data[0],
        "training_status": TRAINING_STATUS.get(status, f"unknown_{status}"),
    }


def parse_ftms_status(data: bytes) -> dict[str, Any]:
    """Decode an FTMS Fitness Machine Status notification."""
    if not data:
        raise ValueError("empty status payload")
    opcode = data[0]
    out: dict[str, Any] = {"status_opcode": opcode}
    if opcode == 0x02 and len(data) >= 2:
        out["stopped_or_paused"] = data[1]
    elif opcode == 0x03:
        out["started_or_resumed"] = True
    elif opcode == 0x04 and len(data) >= 3:
        out["target_speed_kmh"] = int.from_bytes(data[1:3], "little") / 100
    elif opcode == 0x05 and len(data) >= 3:
        out["target_inclination_pct"] = int.from_bytes(data[1:3], "little", signed=True) / 10
    elif opcode == 0x06 and len(data) >= 2:
        out["target_resistance_level"] = data[1] / 10
    elif opcode == 0x07 and len(data) >= 3:
        out["target_power_w"] = int.from_bytes(data[1:3], "little", signed=True)
    elif opcode == 0x08 and len(data) >= 2:
        out["target_heart_rate_bpm"] = data[1]
    elif opcode == 0x11 and len(data) >= 6:
        out["simulation_wind_mps"] = int.from_bytes(data[1:3], "little", signed=True) / 1000
        out["simulation_grade_pct"] = int.from_bytes(data[3:5], "little", signed=True) / 100
        out["simulation_crr"] = data[5] / 10000
        if len(data) >= 7:
            out["simulation_cw"] = data[6] / 100
    elif opcode == 0x14 and len(data) >= 3:
        out["target_cadence_rpm"] = int.from_bytes(data[1:3], "little") / 2
    elif opcode == 0x80:
        out["control_permission_lost"] = True
    return out


def ftms_request_control() -> bytes:
    return b"\x00"


def ftms_reset() -> bytes:
    return b"\x01"


def ftms_start() -> bytes:
    return b"\x07"


def ftms_stop() -> bytes:
    return b"\x08\x01"


def ftms_target_power(watts: float) -> bytes:
    return b"\x05" + struct.pack("<h", max(-1, min(32767, int(round(watts)))))


def ftms_target_cadence(rpm: float) -> bytes:
    return b"\x14" + struct.pack("<H", max(0, min(65535, int(round(rpm * 2)))))


def ftms_simulation_parameters(
    grade_pct: float,
    *,
    wind_mps: float = 0.0,
    rolling_resistance: float = 0.004,
    wind_resistance: float = 0.51,
) -> bytes:
    """Build Set Indoor Bike Simulation Parameters (0x11).

    Units: wind 0.001 m/s, grade 0.01 %, rolling resistance 0.0001,
    wind resistance 0.01 kg/m.
    """
    return b"\x11" + struct.pack(
        "<hhBB",
        max(-32768, min(32767, int(round(wind_mps * 1000)))),
        max(-32768, min(32767, int(round(grade_pct * 100)))),
        max(0, min(255, int(round(rolling_resistance * 10000)))),
        max(0, min(255, int(round(wind_resistance * 100)))),
    )


# ---------------------------------------------------------------------------
# KICKR BIKE shifter buttons
# ---------------------------------------------------------------------------

# 3-byte notifications: PP QQ = button id, RR bit 7 = pressed, bits 0-6 = sequence.
# The id map is from the official KICKR BIKE 1/2 shifter layout as decoded by
# the OpenBikeControl project.
KICKR_BUTTONS: dict[str, tuple[str, str]] = {
    "0200": ("left_up", "Left up"),
    "0400": ("left_down", "Left down"),
    "2000": ("left_steer", "Left steer"),
    "0001": ("right_up", "Right up"),
    "8000": ("right_down", "Right down"),
    "0008": ("right_steer", "Right steer"),
    "1000": ("left_shift_up", "Left shift up"),
    "0800": ("left_shift_down", "Left shift down"),
    "0004": ("right_shift_up", "Right shift up"),
    "0002": ("right_shift_down", "Right shift down"),
    "0100": ("left_brake", "Left brake"),
    "4000": ("right_brake", "Right brake"),
}


def parse_kickr_button_frame(data: bytes) -> dict[str, Any] | None:
    """Decode a KICKR BIKE shifter button notification.

    Returns None for the periodic long configuration frames (which start with
    ``FF 0F`` and are 15 bytes long) and for unknown button ids.
    """
    if len(data) != 3:
        return None
    prefix = data[0:2].hex().upper()
    button = KICKR_BUTTONS.get(prefix)
    if button is None:
        return None
    key, name = button
    return {
        "prefix": prefix,
        "key": key,
        "name": name,
        "pressed": bool(data[2] & 0x80),
        "sequence": data[2] & 0x7F,
    }


# ---------------------------------------------------------------------------
# HEADWIND
# ---------------------------------------------------------------------------

HEADWIND_MODE_OFF = 1
HEADWIND_MODE_HEART_RATE = 2
HEADWIND_MODE_SPEED = 3
HEADWIND_MODE_MANUAL = 4
HEADWIND_MODE_NAMES = {
    HEADWIND_MODE_OFF: "off",
    HEADWIND_MODE_HEART_RATE: "heart_rate",
    HEADWIND_MODE_SPEED: "speed",
    HEADWIND_MODE_MANUAL: "manual",
}


def parse_headwind_status(data: bytes) -> dict[str, Any]:
    """Decode a HEADWIND status notification.

    Confirmed formats:
      fd 01 SS MM   current state, MM=01 off, 02 heart rate, 03 speed, 04 manual
      fe 02 01 SS   speed changed (SS)
      fe 04 01 01   turned off
    """
    if len(data) >= 4 and data[0] == 0xFD:
        mode = data[3]
        speed = data[2]
        return {
            "mode": mode,
            "speed_pct": min(100, speed),
            "is_on": mode != HEADWIND_MODE_OFF and speed > 0,
        }
    if len(data) >= 4 and data[0] == 0xFE:
        if data[1] == 0x02:
            speed = min(100, data[3])
            return {
                "mode": HEADWIND_MODE_MANUAL,
                "speed_pct": speed,
                "is_on": speed > 0,
            }
        if data[1] == 0x04 and data[3] == 0x01:
            return {
                "mode": HEADWIND_MODE_OFF,
                "speed_pct": 0,
                "is_on": False,
            }
    return {}


def headwind_set_mode(mode: int) -> bytes:
    return bytes((0x04, max(HEADWIND_MODE_OFF, min(HEADWIND_MODE_MANUAL, int(mode))), 0x00, 0x00))


def headwind_manual_mode() -> bytes:
    return headwind_set_mode(HEADWIND_MODE_MANUAL)


def headwind_set_speed(speed_pct: int) -> bytes:
    return bytes((0x02, max(0, min(100, int(speed_pct))), 0x00, 0x00))


def headwind_off() -> bytes:
    return bytes((0x04, 0x01, 0x00, 0x00))
