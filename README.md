# Wahoo Fitness for Home Assistant

Home Assistant integration for the **Wahoo KICKR BIKE** and **Wahoo KICKR HEADWIND**.

It connects directly over Bluetooth Low Energy using Home Assistant's Bluetooth
integration (a local adapter or an ESPHome Bluetooth proxy both work). No cloud
account, Wahoo app, or internet connection is required at runtime.

## Features

### KICKR BIKE

Sensors:

- Power (W)
- Cadence (rpm)
- Speed (km/h)
- Session distance (km, integrated from speed and restored after restarts)
- Front / rear gear (1-based) and gear counts
- Training status
- Connected and pedaling binary sensors

Controls:

- **Target power** (ERG mode), 0–2000 W
- **Simulated grade**, −15 % to +20 %
- **Control mode** select: Off, ERG, Simulation

Setting target power automatically selects ERG; setting grade automatically
selects Simulation. Selecting Off stops the workout.

> Resistance-level control is intentionally not exposed: the KICKR BIKE does not
> advertise the FTMS resistance target feature and rejects the corresponding
> command. Use ERG or simulation grade instead.

> Virtual gear shifting is not exposed. The physical shifters and third-party
> apps update the gear sensors, but the shift command lives in Wahoo's native
> library and is not publicly documented. See [PROTOCOL.md](PROTOCOL.md).

### KICKR HEADWIND

- Fan entity with on/off and 0–100 % speed
- Mode sensor (`off`, `auto`, `manual`)
- Connected binary sensor

Setting a speed puts the fan in manual mode. The fan's automatic heart-rate /
power mode can still be configured in the Wahoo app; the mode sensor will report
`auto` while it is active.

## Requirements

- Home Assistant 2025.1 or newer
- A Bluetooth adapter (or ESPHome Bluetooth proxy) in range of the devices
- KICKR BIKE firmware with FTMS support (tested on 1.27.0)
- HEADWIND firmware 1.0.3 (tested)

## Installation with HACS

1. In Home Assistant open **HACS → Integrations**.
2. Open the three-dot menu → **Custom repositories**.
3. Add this repository URL, category **Integration**.
4. Install **Wahoo Fitness** and restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration → Wahoo Fitness**.

The devices are also auto-discovered over Bluetooth; a notification will offer to
add them when they are awake and in range.

## Setup notes

- Wake the KICKR BIKE (pedal briefly) and the HEADWIND (press its power button)
  before adding them.
- Each device gets its own config entry and device page.
- The integration keeps a BLE connection open. If the Wahoo app, Zwift, or
  another trainer app takes control of the KICKR BIKE, ERG/grade commands will
  fail with a "control unavailable" error while sensor data continues to work.
- BLE addresses on these devices are random static addresses. The integration
  identifies devices by their advertised name suffix (for example
  `KICKR BIKE ABCD`) and automatically updates the stored address if it changes.

## Entity overview

For a bike named `KICKR BIKE ABCD`:

| Entity | Example |
| --- | --- |
| `sensor.kickr_bike_abcd_power` | 215 W |
| `sensor.kickr_bike_abcd_cadence` | 92 rpm |
| `sensor.kickr_bike_abcd_speed` | 31.4 km/h |
| `sensor.kickr_bike_abcd_session_distance` | 12.347 km |
| `sensor.kickr_bike_abcd_front_gear` | 2 |
| `sensor.kickr_bike_abcd_rear_gear` | 7 |
| `number.kickr_bike_abcd_target_power` | 180 W |
| `number.kickr_bike_abcd_grade` | 3.5 % |
| `select.kickr_bike_abcd_control_mode` | ERG / Simulation / Off |

For a fan named `HEADWIND 1234`:

| Entity | Example |
| --- | --- |
| `fan.headwind_1234` | on, 45 % |
| `sensor.headwind_1234_mode` | manual |
| `binary_sensor.headwind_1234_connected` | on |

## Troubleshooting

- **Device not discovered:** make sure it is awake and not connected to a phone
  or another app. Check **Settings → Devices & services → Bluetooth** for the
  adapter/proxy and its range.
- **Sensors work but controls fail:** another app holds FTMS control. Close it
  and wait up to 30 seconds; the integration retries automatically.
- **Entity names:** the device name comes from the BLE advertisement. Renaming a
  device in the Wahoo app changes its name; update or re-add the config entry.
- **Diagnostics:** download diagnostics from the integration page to see the
  connection state, firmware, serial number and last decoded data.

## Development

Protocol notes and captured frames are in [PROTOCOL.md](PROTOCOL.md).

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install pytest pytest-homeassistant-custom-component ruff
pytest -q
ruff check .
```

The test suite uses a fake BLE client, so no hardware is needed.

## License

MIT — see [LICENSE](LICENSE).
