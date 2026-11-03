"""Tests for the Wahoo Fitness BLE protocol helpers."""

from __future__ import annotations

from protocol import (
    ftms_request_control,
    ftms_reset,
    ftms_simulation_parameters,
    ftms_start,
    ftms_stop,
    ftms_target_power,
    headwind_manual_mode,
    headwind_off,
    headwind_set_speed,
    parse_cps_measurement,
    parse_ftms_control_response,
    parse_ftms_status,
    parse_gear_state,
    parse_headwind_status,
    parse_indoor_bike_data,
    parse_training_status,
)


def test_indoor_bike_data_idle() -> None:
    data = bytes.fromhex("44 00 00 00 00 00 00 00")
    parsed = parse_indoor_bike_data(data)
    assert parsed["flags"] == 0x0044
    assert parsed["speed_kmh"] == 0
    assert parsed["cadence_rpm"] == 0
    assert parsed["power_w"] == 0


def test_indoor_bike_data_all_fields() -> None:
    # flags: speed, avg speed, cadence, avg cadence, distance, resistance,
    # power, avg power, energy, energy/hour, energy/min, HR, MET,
    # elapsed, remaining.  Bit 0 is clear => speed present.
    flags = 0x7FFE
    payload = bytearray(flags.to_bytes(2, "little"))
    payload += (2500).to_bytes(2, "little")  # 25.00 km/h
    payload += (2400).to_bytes(2, "little")  # 24.00 km/h
    payload += (180).to_bytes(2, "little")  # 90 rpm
    payload += (176).to_bytes(2, "little")  # 88 rpm
    payload += (123456).to_bytes(3, "little")
    payload += (75).to_bytes(2, "little")  # 7.5 %
    payload += (200).to_bytes(2, "little", signed=True)
    payload += (190).to_bytes(2, "little", signed=True)
    payload += (500).to_bytes(2, "little")
    payload += (600).to_bytes(2, "little")
    payload += (10).to_bytes(2, "little")
    payload += bytes([145])
    payload += bytes([85])
    payload += (3600).to_bytes(2, "little")
    payload += (120).to_bytes(2, "little")

    parsed = parse_indoor_bike_data(bytes(payload))
    assert parsed["speed_kmh"] == 25
    assert parsed["average_speed_kmh"] == 24
    assert parsed["cadence_rpm"] == 90
    assert parsed["average_cadence_rpm"] == 88
    assert parsed["distance_m"] == 123456
    assert parsed["resistance_level"] == 7.5
    assert parsed["power_w"] == 200
    assert parsed["average_power_w"] == 190
    assert parsed["total_energy_kcal"] == 500
    assert parsed["heart_rate_bpm"] == 145
    assert parsed["metabolic_equivalent"] == 8.5
    assert parsed["elapsed_time_s"] == 3600


def test_cps_measurement_live_capture() -> None:
    data = bytes.fromhex("3c 00 00 00 c1 47 46 9e 00 00 ec 7c d1 5e 4f 00")
    parsed = parse_cps_measurement(data)
    assert parsed["power_w"] == 0
    assert parsed["wheel_revolutions"] == 0x9E46
    assert parsed["wheel_event_time_s"] == 0x7CEC / 1024
    assert parsed["crank_revolutions"] == 0x5ED1
    assert parsed["crank_event_time_s"] == 0x004F / 1024


def test_gear_state_live_capture() -> None:
    data = bytes.fromhex("07 00 00 02 02 0c 00 00 00 00 00")
    parsed = parse_gear_state(data)
    assert parsed == {
        "front_gear_index": 0,
        "rear_gear_index": 2,
        "front_gear_count": 2,
        "rear_gear_count": 12,
    }


def test_headwind_status_manual_on() -> None:
    parsed = parse_headwind_status(bytes.fromhex("fd 01 19 04"))
    assert parsed == {"mode": 4, "speed_pct": 25, "is_on": True}


def test_headwind_status_off() -> None:
    parsed = parse_headwind_status(bytes.fromhex("fd 01 00 01"))
    assert parsed == {"mode": 1, "speed_pct": 0, "is_on": False}


def test_headwind_status_speed_ack() -> None:
    parsed = parse_headwind_status(bytes.fromhex("fe 02 01 3c"))
    assert parsed == {"mode": 4, "speed_pct": 60, "is_on": True}


def test_headwind_status_unknown() -> None:
    assert parse_headwind_status(b"\x00\x01\x02\x03") == {}


def test_headwind_commands() -> None:
    assert headwind_manual_mode() == bytes.fromhex("04 04 00 00")
    assert headwind_set_speed(20) == bytes.fromhex("02 14 00 00")
    assert headwind_set_speed(1000) == bytes.fromhex("02 64 00 00")
    assert headwind_off() == bytes.fromhex("04 01 00 00")


def test_ftms_commands() -> None:
    assert ftms_request_control() == b"\x00"
    assert ftms_start() == b"\x07"
    assert ftms_stop() == b"\x08\x01"
    assert ftms_reset() == b"\x01"
    assert ftms_target_power(120) == bytes.fromhex("05 78 00")
    assert ftms_simulation_parameters(-5) == bytes.fromhex("11 00 00 0c fe 28 33")


def test_ftms_control_response() -> None:
    response = parse_ftms_control_response(bytes.fromhex("80 05 01"))
    assert response is not None
    assert response.opcode == 0x05
    assert response.success
    assert response.description == "success"

    response = parse_ftms_control_response(bytes.fromhex("80 04 04"))
    assert response is not None
    assert not response.success
    assert response.description == "operation failed"


def test_ftms_status() -> None:
    assert parse_ftms_status(bytes.fromhex("07 78 00")) == {
        "status_opcode": 0x07,
        "target_power_w": 120,
    }
    assert parse_ftms_status(bytes.fromhex("11 00 00 0c fe 28 33")) == {
        "status_opcode": 0x11,
        "simulation_wind_mps": 0,
        "simulation_grade_pct": -5,
        "simulation_crr": 0.004,
        "simulation_cw": 0.51,
    }


def test_training_status() -> None:
    assert parse_training_status(bytes.fromhex("cc a0"))["training_status"] == "unknown_160"
    assert parse_training_status(bytes.fromhex("00 01"))["training_status"] == "idle"
