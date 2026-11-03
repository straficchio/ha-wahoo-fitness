"""Bluetooth coordinators for Wahoo Fitness devices."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any, override

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_register_callback,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ADDRESS,
    CONF_MODEL,
    CONF_NAME,
    CONNECT_TIMEOUT,
    CONTROL_RETRY_INTERVAL,
    DATA_WATCHDOG,
    DOMAIN,
    MANUFACTURER,
    MAX_GRADE,
    MIN_GRADE,
    MODE_ERG,
    MODE_OFF,
    MODE_SIMULATION,
    MODEL_NAMES,
    PUSH_INTERVAL,
    RECONNECT_DELAY,
)
from .protocol import (
    CPS_MEASUREMENT_UUID,
    DEVICE_NAME_UUID,
    FIRMWARE_REVISION_UUID,
    FTMS_CONTROL_POINT_UUID,
    FTMS_INDOOR_BIKE_DATA_UUID,
    FTMS_STATUS_UUID,
    FTMS_TRAINING_STATUS_UUID,
    HARDWARE_REVISION_UUID,
    HEADWIND_CONTROL_UUID,
    KICKR_GEAR_STATE_UUID,
    KICKR_SHIFTER_BUTTON_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
    SERIAL_NUMBER_UUID,
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

_LOGGER = logging.getLogger(__name__)

type WahooData = dict[str, Any]


class WahooFitnessCoordinator(DataUpdateCoordinator[WahooData]):
    """Maintain a connection to one Wahoo BLE device."""

    _watchdog = DATA_WATCHDOG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self.model: str = entry.data[CONF_MODEL]
        self.device_name: str = entry.data[CONF_NAME]
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=self.device_name,
            update_interval=None,
            always_update=False,
        )
        self.data = {}
        self.connected = False
        self.control_available = False
        self.serial_number: str | None = None
        self.gatt_name: str | None = None
        self.manufacturer: str | None = None
        self.model_number: str | None = None
        self.firmware_version: str | None = None
        self.hardware_version: str | None = None
        self.rssi: int | None = None

        self._client: BleakClient | None = None
        self._client_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_notification = 0.0
        self._last_advertisement = 0.0
        self._last_push = 0.0
        self._push_unsub: CALLBACK_TYPE | None = None
        self._last_control_attempt = 0.0
        self._control_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._control_lock = asyncio.Lock()
        self._started = False
        self._adv_unsub: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Start the background connection loop."""
        self._adv_unsub = async_register_callback(
            self.hass,
            self._async_advertisement,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.PASSIVE,
        )
        self._task = self.hass.async_create_background_task(
            self._async_run(), f"{DOMAIN} {self.address}"
        )

    @callback
    def async_stop(self) -> None:
        """Stop the background connection loop."""
        self._stop.set()
        if self._adv_unsub is not None:
            self._adv_unsub()
            self._adv_unsub = None
        if self._push_unsub is not None:
            self._push_unsub()
            self._push_unsub = None
        if self._task is not None:
            self._task.cancel()
            self._task = None
            self.hass.async_create_task(
                self._async_disconnect(), f"{DOMAIN} disconnect {self.address}"
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device registry metadata."""
        info = DeviceInfo(
            identifiers={(DOMAIN, self.entry.unique_id or self.address)},
            name=self.device_name,
            manufacturer=self.manufacturer or MANUFACTURER,
            model=MODEL_NAMES.get(self.model, self.model),
        )
        if self.model_number:
            info["model_id"] = self.model_number
        if self.serial_number:
            info["serial_number"] = self.serial_number
        if self.firmware_version:
            info["sw_version"] = self.firmware_version
        if self.hardware_version:
            info["hw_version"] = self.hardware_version
        return info

    # ------------------------------------------------------------------
    # Connection loop
    # ------------------------------------------------------------------

    async def _async_run(self) -> None:
        """Keep the device connected, reconnecting forever until stopped."""
        while not self._stop.is_set():
            try:
                await self._async_connect()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.debug("Unexpected error talking to %s", self.address, exc_info=True)
            finally:
                await self._async_disconnect()
                self.connected = False
                self._async_push(force=True)

            if self._stop.is_set():
                break
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=RECONNECT_DELAY)

    async def _async_connect(self) -> None:
        """Open one connection and run the session until it drops."""
        device = async_ble_device_from_address(self.hass, self.address, True)
        if device is None:
            _LOGGER.debug("%s (%s) is not in range", self.name, self.address)
            return

        _LOGGER.debug("Connecting to %s (%s)", self.name, self.address)
        client = await establish_connection(
            BleakClient,
            device,
            self.address,
            disconnected_callback=self._async_disconnected,
            max_attempts=1,
            timeout=CONNECT_TIMEOUT,
        )
        async with self._client_lock:
            self._client = client
        try:
            # Subclasses need to use the control characteristic during setup,
            # so mark the connection live before subscribing.
            self.connected = True
            await self._async_setup(client)
            self._last_notification = time.monotonic()
            self._async_push(force=True)
            _LOGGER.debug("Connected to %s", self.name)
            await self._async_run_session(client)
        finally:
            self.connected = False
            self._async_push(force=True)

    async def _async_run_session(self, client: BleakClient) -> None:
        """Watch for a stalled connection."""
        while client.is_connected and not self._stop.is_set():
            await asyncio.sleep(1)
            if time.monotonic() - self._last_notification > self._watchdog:
                _LOGGER.debug("No data from %s for %ss, reconnecting", self.name, self._watchdog)
                break

    async def _async_disconnect(self) -> None:
        async with self._client_lock:
            client, self._client = self._client, None
        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except (BleakError, TimeoutError):
                _LOGGER.debug("Error disconnecting from %s", self.name, exc_info=True)

    @callback
    def _async_disconnected(self, _client: BleakClient) -> None:
        self.connected = False

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    async def _async_setup(self, client: BleakClient) -> None:
        """Subscribe to notifications and read metadata."""
        await self._async_read_device_info(client)
        await self._async_subscribe(client)

    async def _async_subscribe(self, client: BleakClient) -> None:
        """Subscribe to device notifications."""
        raise NotImplementedError

    @callback
    def _async_handle_notification(self, uuid: str, payload: bytes) -> None:
        """Handle a notification. Implemented by subclasses."""
        raise NotImplementedError

    @callback
    def _async_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        """Remember advertisement signal strength."""
        self._last_advertisement = time.monotonic()
        if service_info.rssi:
            self.rssi = service_info.rssi

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _async_start_notify(self, client: BleakClient, uuid: str) -> None:
        try:
            await client.start_notify(uuid, self._dispatch_notification)
        except (BleakError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Could not subscribe to %s on %s: %s", uuid, self.name, err)

    @callback
    def _dispatch_notification(self, characteristic: Any, data: bytearray) -> None:
        uuid = characteristic.uuid.lower()
        try:
            self._async_handle_notification(uuid, bytes(data))
        except (ValueError, IndexError) as err:
            _LOGGER.debug("Invalid notification from %s (%s): %s", self.name, uuid, err)
            return
        self._last_notification = time.monotonic()
        self._async_push()

    @callback
    def _async_push(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_push < PUSH_INTERVAL:
            if self._push_unsub is None:
                self._push_unsub = async_call_later(
                    self.hass,
                    PUSH_INTERVAL - (now - self._last_push),
                    self._async_push_scheduled,
                )
            return
        if self._push_unsub is not None:
            self._push_unsub()
            self._push_unsub = None
        self._last_push = now
        self.async_set_updated_data(dict(self.data))

    @callback
    def _async_push_scheduled(self, _now: Any) -> None:
        """Deliver a trailing update after throttling."""
        self._push_unsub = None
        self._last_push = time.monotonic()
        self.async_set_updated_data(dict(self.data))

    async def _async_read_device_info(self, client: BleakClient) -> None:
        """Read the Device Information service."""
        values = {
            "manufacturer": (MANUFACTURER_NAME_UUID, "str"),
            "model_number": (MODEL_NUMBER_UUID, "str"),
            "serial_number": (SERIAL_NUMBER_UUID, "str"),
            "firmware_version": (FIRMWARE_REVISION_UUID, "str"),
            "hardware_version": (HARDWARE_REVISION_UUID, "str"),
            "gatt_name": (DEVICE_NAME_UUID, "str"),
        }
        for attr, (uuid, kind) in values.items():
            try:
                raw = await client.read_gatt_char(uuid)
            except (BleakError, TimeoutError, ValueError):
                continue
            if kind == "str":
                setattr(self, attr, raw.decode("utf-8", errors="replace").strip() or None)

    async def _async_control(
        self,
        command: bytes,
        expected_opcode: int,
        timeout: float = 4.0,
        *,
        require_control: bool = True,
    ) -> None:
        """Write an FTMS control command and wait for its indication."""
        client = self._client
        if not self.connected or client is None or not client.is_connected:
            raise HomeAssistantError(f"{self.name} is not connected")
        if require_control and not self.control_available:
            raise HomeAssistantError(
                f"{self.name} control is unavailable (another app may be connected)"
            )

        async with self._control_lock:
            while not self._control_queue.empty():
                self._control_queue.get_nowait()
            try:
                await client.write_gatt_char(FTMS_CONTROL_POINT_UUID, command, response=True)
            except (BleakError, TimeoutError) as err:
                raise HomeAssistantError(f"Could not send command to {self.name}: {err}") from err

            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HomeAssistantError(
                        f"Timed out waiting for {self.name} to acknowledge the command"
                    )
                try:
                    payload = await asyncio.wait_for(self._control_queue.get(), timeout=remaining)
                except TimeoutError as err:
                    raise HomeAssistantError(
                        f"Timed out waiting for {self.name} to acknowledge the command"
                    ) from err
                response = parse_ftms_control_response(payload)
                if response is None or response.opcode != expected_opcode:
                    continue
                if not response.success:
                    raise HomeAssistantError(
                        f"{self.name} rejected the command: {response.description}"
                    )
                return

    async def async_request_control(self) -> bool:
        """Try to take FTMS control. Returns True on success."""
        if self.control_available:
            return True
        if not self.connected or self._client is None:
            return False
        if time.monotonic() - self._last_control_attempt < CONTROL_RETRY_INTERVAL:
            return False
        self._last_control_attempt = time.monotonic()
        try:
            await self._async_control(
                ftms_request_control(), 0x00, timeout=4.0, require_control=False
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Could not take control of %s: %s", self.name, err)
            self.control_available = False
            return False
        self.control_available = True
        self._async_push(force=True)
        return True

    async def async_reset(self) -> None:
        """Reset the workout on an FTMS device."""
        await self._async_control(ftms_reset(), 0x01)
        self.control_available = False
        self._started = False
        self.data["mode"] = MODE_OFF
        self._async_push(force=True)
        await self.async_request_control()


class KickrBikeCoordinator(WahooFitnessCoordinator):
    """Coordinator for a Wahoo KICKR BIKE."""

    @override
    async def _async_subscribe(self, client: BleakClient) -> None:
        for uuid in (
            FTMS_INDOOR_BIKE_DATA_UUID,
            CPS_MEASUREMENT_UUID,
            FTMS_CONTROL_POINT_UUID,
            FTMS_STATUS_UUID,
            FTMS_TRAINING_STATUS_UUID,
            KICKR_GEAR_STATE_UUID,
            KICKR_SHIFTER_BUTTON_UUID,
        ):
            await self._async_start_notify(client, uuid)

    @override
    async def _async_setup(self, client: BleakClient) -> None:
        # A reconnect always loses FTMS control; keep the last target values
        # but report the mode as off until a new command is accepted.
        self.control_available = False
        self._started = False
        self.data["mode"] = MODE_OFF
        await super()._async_setup(client)
        await self.async_request_control()

    @override
    async def _async_run_session(self, client: BleakClient) -> None:
        while client.is_connected and not self._stop.is_set():
            await asyncio.sleep(1)
            if (
                not self.control_available
                and time.monotonic() - self._last_control_attempt >= CONTROL_RETRY_INTERVAL
            ):
                await self.async_request_control()
            if time.monotonic() - self._last_notification > self._watchdog:
                _LOGGER.debug("No data from %s for %ss, reconnecting", self.name, self._watchdog)
                break

    @callback
    @override
    def _async_handle_notification(self, uuid: str, payload: bytes) -> None:
        if uuid == FTMS_INDOOR_BIKE_DATA_UUID:
            self.data.update(parse_indoor_bike_data(payload))
        elif uuid == CPS_MEASUREMENT_UUID:
            measurement = parse_cps_measurement(payload)
            # FTMS is the primary source, but CPS provides wheel revolutions.
            if "power_w" not in self.data:
                self.data["power_w"] = measurement["power_w"]
            if "wheel_revolutions" in measurement:
                self.data["wheel_revolutions"] = measurement["wheel_revolutions"]
        elif uuid == KICKR_GEAR_STATE_UUID:
            gear = parse_gear_state(payload)
            self.data["front_gear"] = gear["front_gear_index"] + 1
            self.data["rear_gear"] = gear["rear_gear_index"] + 1
            self.data["front_gear_count"] = gear["front_gear_count"]
            self.data["rear_gear_count"] = gear["rear_gear_count"]
        elif uuid == FTMS_TRAINING_STATUS_UUID:
            self.data.update(parse_training_status(payload))
        elif uuid == FTMS_STATUS_UUID:
            status = parse_ftms_status(payload)
            self.data.update(status)
            if status.get("started_or_resumed"):
                self._started = True
            elif status.get("control_permission_lost"):
                self.control_available = False
                self.data["mode"] = MODE_OFF
            elif "target_power_w" in status:
                self.data["mode"] = MODE_ERG
                self.data["target_power_w"] = status["target_power_w"]
            elif "simulation_grade_pct" in status:
                self.data["mode"] = MODE_SIMULATION
                self.data["target_grade_pct"] = status["simulation_grade_pct"]
            elif "stopped_or_paused" in status:
                self.data["mode"] = MODE_OFF
        elif uuid == FTMS_CONTROL_POINT_UUID:
            self._control_queue.put_nowait(payload)
        # KICKR_SHIFTER_BUTTON_UUID carries shifter button events; currently unused.

    async def _async_ensure_started(self) -> None:
        if self._started:
            return
        await self._async_control(ftms_start(), 0x07)
        self._started = True

    async def async_set_target_power(self, watts: float) -> None:
        """Set ERG target power in watts."""
        await self._async_ensure_started()
        await self._async_control(ftms_target_power(watts), 0x05)
        self.data["target_power_w"] = float(watts)
        self.data["mode"] = MODE_ERG
        self._async_push(force=True)

    async def async_set_grade(self, grade_pct: float) -> None:
        """Set simulated grade in percent."""
        grade = max(MIN_GRADE, min(MAX_GRADE, grade_pct))
        await self._async_ensure_started()
        await self._async_control(ftms_simulation_parameters(grade), 0x11)
        self.data["target_grade_pct"] = grade
        self.data["mode"] = MODE_SIMULATION
        self._async_push(force=True)

    async def async_stop_workout(self) -> None:
        """Stop the current workout."""
        await self._async_control(ftms_stop(), 0x08)
        self.data["mode"] = MODE_OFF
        self._started = False
        self._async_push(force=True)

    async def async_set_mode(self, mode: str) -> None:
        """Switch control mode."""
        if mode == MODE_OFF:
            await self.async_stop_workout()
        elif mode == MODE_ERG:
            target = self.data.get("target_power_w")
            await self.async_set_target_power(100 if target is None else float(target))
        elif mode == MODE_SIMULATION:
            target = self.data.get("target_grade_pct")
            await self.async_set_grade(0 if target is None else float(target))
        else:
            raise HomeAssistantError(f"Unknown control mode: {mode}")


class HeadwindCoordinator(WahooFitnessCoordinator):
    """Coordinator for a Wahoo KICKR HEADWIND fan."""

    @override
    async def _async_subscribe(self, client: BleakClient) -> None:
        await self._async_start_notify(client, HEADWIND_CONTROL_UUID)
        # HEADWIND usually emits its state before the subscription completes,
        # so read the characteristic once to avoid an unknown initial state.
        try:
            payload = await client.read_gatt_char(HEADWIND_CONTROL_UUID)
        except (BleakError, TimeoutError, ValueError):
            return
        self._async_handle_notification(HEADWIND_CONTROL_UUID, bytes(payload))

    @callback
    @override
    def _async_handle_notification(self, uuid: str, payload: bytes) -> None:
        if uuid != HEADWIND_CONTROL_UUID:
            return
        status = parse_headwind_status(payload)
        if status:
            self.data.update(status)

    async def _async_write(self, payload: bytes) -> None:
        client = self._client
        if not self.connected or client is None or not client.is_connected:
            raise HomeAssistantError(f"{self.name} is not connected")
        try:
            await client.write_gatt_char(HEADWIND_CONTROL_UUID, payload, response=False)
        except (BleakError, TimeoutError) as err:
            raise HomeAssistantError(f"Could not send command to {self.name}: {err}") from err

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed 0-100 %."""
        percentage = max(0, min(100, int(percentage)))
        if percentage == 0:
            await self.async_turn_off()
            return
        await self._async_write(headwind_manual_mode())
        await self._async_write(headwind_set_speed(percentage))
        self.data["speed_pct"] = percentage
        self.data["is_on"] = True
        self.data["mode"] = 4
        self._async_push(force=True)

    async def async_turn_off(self) -> None:
        await self._async_write(headwind_off())
        self.data["speed_pct"] = 0
        self.data["is_on"] = False
        self.data["mode"] = 1
        self._async_push(force=True)

    async def async_turn_on(self, percentage: int | None = None) -> None:
        if percentage is None:
            percentage = int(self.data.get("speed_pct") or 25) or 25
        await self.async_set_percentage(percentage)
