"""Diagnostics support for the Wahoo Fitness integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import WahooFitnessCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: WahooFitnessCoordinator = entry.runtime_data
    return {
        "model": coordinator.model,
        "name": coordinator.device_name,
        "address": coordinator.address,
        "connected": coordinator.connected,
        "control_available": coordinator.control_available,
        "rssi": coordinator.rssi,
        "manufacturer": coordinator.manufacturer,
        "model_number": coordinator.model_number,
        "gatt_name": coordinator.gatt_name,
        "serial_number": coordinator.serial_number,
        "firmware_version": coordinator.firmware_version,
        "hardware_version": coordinator.hardware_version,
        "data": dict(coordinator.data),
    }
