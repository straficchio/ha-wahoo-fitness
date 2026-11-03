"""The Wahoo Fitness integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL, MODEL_HEADWIND, MODEL_KICKR_BIKE
from .coordinator import (
    HeadwindCoordinator,
    KickrBikeCoordinator,
    WahooFitnessCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.FAN,
]

type WahooFitnessConfigEntry = ConfigEntry[WahooFitnessCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: WahooFitnessConfigEntry) -> bool:
    """Set up a Wahoo Fitness device from a config entry."""
    model = entry.data[CONF_MODEL]
    if model == MODEL_KICKR_BIKE:
        coordinator: WahooFitnessCoordinator = KickrBikeCoordinator(hass, entry)
    elif model == MODEL_HEADWIND:
        coordinator = HeadwindCoordinator(hass, entry)
    else:
        _LOGGER.error("Unsupported Wahoo Fitness model: %s", model)
        return False

    entry.runtime_data = coordinator
    await coordinator.async_start()
    entry.async_on_unload(coordinator.async_stop)

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        coordinator.async_stop()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WahooFitnessConfigEntry) -> bool:
    """Unload a Wahoo Fitness config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
