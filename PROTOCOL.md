# Protocol notes

These notes were derived from live captures (KICKR BIKE firmware 1.27.0,
HEADWIND firmware 1.0.3) and from the Wahoo Android app 7.4.0. They document the
parts used by this integration. They are not a complete specification.

## Device discovery

| Device | Advertised name | Advertised services |
| --- | --- | --- |
| KICKR BIKE | `KICKR BIKE ABCD` | `0x1818`, `0x1826`, `a026ee0d-…` |
| HEADWIND | `HEADWIND 1234` | none in the advertisement packet |

Both devices use a random static BLE address. The name suffix (last four hex
characters) is stable and is what the integration uses as its identity.

## Wahoo UUIDs

Wahoo BLE characteristics are generated as:

```
A026<code:04x>-0A7D-4AB3-97FA-F1500F9FEB8B
```

Examples from the app's `CruxBtleCharacteristicType` enum:

| Code | Name | UUID |
| --- | --- | --- |
| `0xE002` | Wahoo command | `a026e002-…` |
| `0xE004` | Wahoo response | `a026e004-…` |
| `0xE005` | Cycling Power Wahoo control point | `a026e005-…` |
| `0xE037` | Advanced trainer control point | `a026e037-…` |
| `0xE038` | Headwind control point | `a026e038-…` |
| `0xE039` | KICKR BIKE control point | `a026e039-…` |
| `0xE03A` | KICKR BIKE status (gear state) | `a026e03a-…` |
| `0xE03B` | KICKR BIKE sensor diagnostics | `a026e03b-…` |
| `0xE03C` | KICKR BIKE shifter button | `a026e03c-…` |

## KICKR BIKE

### GATT services used

| Service | Characteristic | Notes |
| --- | --- | --- |
| Fitness Machine `0x1826` | `0x2AD2` Indoor Bike Data | notify |
| | `0x2AD9` Control Point | write + indicate |
| | `0x2ADA` Status | notify |
| | `0x2AD3` Training Status | notify |
| Cycling Power `0x1818` | `0x2A63` Measurement | notify |
| Wahoo `a026ee0d-…` | `0xE03A` gear state | notify |
| | `0xE03C` shifter button | notify (not used) |
| Wahoo `a026ee0b-…` | `0xE037` advanced trainer CP | read/write/notify (not used) |

### FTMS control point

Commands are written with response and answered by an indication
`80 <request opcode> <result>`, where result `01` is success.

Used commands:

| Opcode | Command | Payload |
| --- | --- | --- |
| `0x00` | Request Control | none |
| `0x01` | Reset | none |
| `0x05` | Set Target Power | `int16` watts |
| `0x07` | Start / Resume | none |
| `0x08` | Stop / Pause | `0x01` (stop) |
| `0x11` | Set Indoor Bike Simulation Parameters | `int16` wind (0.001 m/s), `int16` grade (0.01 %), `uint8` Crr (0.0001), `uint8` Cw (0.01 kg/m) |
| `0x12` | Set Wheel Circumference | `uint16` (0.1 mm) |

Observed responses on firmware 1.27.0:

```
00 -> 80 00 01   success
07 -> 80 07 01   success
05 78 00 -> 80 05 01   success (120 W)
11 00 00 00 00 28 33 -> 80 11 01   success (0 %, Crr 0.004, Cw 0.51)
08 01 -> 80 08 01   success (stop)
01 -> 80 01 01   success (reset)
04 32 -> 80 04 04   operation failed (resistance target not supported)
```

The bike reports only these target-setting features: power target, indoor bike
simulation parameters, and wheel circumference. This is why the integration does
not expose resistance-level control.

### Indoor Bike Data

The observed flags are `0x0044`:

- bit 0 clear → instantaneous speed present (`uint16`, 0.01 km/h)
- bit 2 → instantaneous cadence present (`uint16`, 0.5 rpm)
- bit 6 → instantaneous power present (`int16`, W)

Even after Start/Resume the bike did not add distance, energy, resistance, or
heart-rate fields. Session distance is therefore integrated from speed.

### Gear state (`0xE03A`)

11-byte notification. Byte layout:

| Offset | Meaning |
| --- | --- |
| 2 | selected front gear, 0-based |
| 3 | selected rear gear, 0-based |
| 4 | number of front gears |
| 5 | number of rear gears |

Live example: `07 00 00 02 02 0c 00 00 00 00 00` → front index 0, rear index 2,
2 chainrings, 12 sprockets. The integration adds 1 for display.

### Shifter button (`0xE03C`) and bike control point (`0xE039`)

Both are handled inside Wahoo's native `libCruxAndroid.so`. The native functions
`crux_codec_btle_kickr_bike_cp_client_encode_req` and
`crux_codec_btle_kickr_bike_shifter_button_client_decode` exist, and the bike
control point uses request types that encode shift/config operations. The exact
command semantics are not documented, so this integration only subscribes to the
gear state and does not send shift commands.

## HEADWIND

### GATT

Service `a026ee0c-…`, characteristic `a026e038-…`
(`read`, `write-without-response`, `notify`). Device Information service
`0x180A` provides manufacturer, serial, firmware and hardware revisions.

### Commands

| Purpose | Bytes |
| --- | --- |
| Enter manual mode | `04 04 00 00` |
| Set speed 1–100 % | `02 <speed> 00 00` |
| Turn off | `04 01 00 00` |

All writes use write-without-response.

### Notifications

| Bytes | Meaning |
| --- | --- |
| `fd 01 <speed> 04` | manual mode, running at `<speed>` % |
| `fd 01 00 01` | off |
| `fd 01 00 03` | auto/standby, speed 0 |
| `fe 02 01 <speed>` | speed acknowledgement |
| `fe 04 01 01` | off acknowledgement |

Live sequence:

```
write 04 04 00 00 -> notify fd 01 19 04   (manual, 25 %)
write 02 14 00 00 -> notify fe 02 01 14, fd 01 14 04   (20 %)
write 02 3c 00 00 -> notify fe 02 01 3c, fd 01 3c 04   (60 %)
write 04 01 00 00 -> notify fe 04 01 01, fd 01 00 01   (off)
```

## Sources

- Live BLE captures with BlueZ/bleak on Linux
- Wahoo Android app 7.4.0 (`com.wahoofitness.fitness`), split APK
- `stareat/wahoo-kickr-bike-shift-display` for the gear-state byte layout
- `garanj/wearwind` and `vvrnv/wahoo-headwind-controller` for independent
  confirmation of the HEADWIND command frames
