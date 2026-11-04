"""Select entities for Wahoo Fitness devices."""

from __future__ import annotations

from typing import override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONTROL_MODE_BY_LABEL,
    CONTROL_MODES,
    MODE_OFF,
    MODEL_HEADWIND,
    MODEL_KICKR_BIKE,
)
from .coordinator import HeadwindCoordinator, KickrBikeCoordinator
from .entity import WahooFitnessEntity
from .protocol import (
    HEADWIND_MODE_HEART_RATE,
    HEADWIND_MODE_MANUAL,
    HEADWIND_MODE_OFF,
    HEADWIND_MODE_SPEED,
)

PARALLEL_UPDATES = 1

CONTROL_MODE_DESCRIPTION = SelectEntityDescription(
    key="control_mode",
    translation_key="control_mode",
    icon="mdi:bike",
)

HEADWIND_MODE_OPTIONS: dict[str, int] = {
    "Off": HEADWIND_MODE_OFF,
    "Heart rate": HEADWIND_MODE_HEART_RATE,
    "Speed": HEADWIND_MODE_SPEED,
    "Manual": HEADWIND_MODE_MANUAL,
}
HEADWIND_MODE_BY_LABEL: dict[str, int] = HEADWIND_MODE_OPTIONS
HEADWIND_LABEL_BY_MODE: dict[int, str] = {
    mode: label for label, mode in HEADWIND_MODE_OPTIONS.items()
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data["model"] == MODEL_KICKR_BIKE:
        coordinator: KickrBikeCoordinator = entry.runtime_data
        async_add_entities([KickrControlModeSelect(coordinator, CONTROL_MODE_DESCRIPTION)])
    elif entry.data["model"] == MODEL_HEADWIND:
        headwind: HeadwindCoordinator = entry.runtime_data
        async_add_entities([HeadwindModeSelect(headwind)])


class KickrControlModeSelect(WahooFitnessEntity, SelectEntity):
    """Select ERG, simulation, or off."""

    entity_description: SelectEntityDescription
    _attr_options = list(CONTROL_MODES.values())

    def __init__(
        self,
        coordinator: KickrBikeCoordinator,
        description: SelectEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"

    @property
    @override
    def current_option(self) -> str | None:
        mode = self.coordinator.data.get("mode", MODE_OFF)
        return CONTROL_MODES.get(mode)

    @override
    async def async_select_option(self, option: str) -> None:
        mode = CONTROL_MODE_BY_LABEL.get(option)
        if mode is None:
            return
        await self.coordinator.async_set_mode(mode)

    @property
    @override
    def available(self) -> bool:
        return self.coordinator.connected


class HeadwindModeSelect(WahooFitnessEntity, SelectEntity):
    """Select the HEADWIND operating mode."""

    _attr_translation_key = "fan_mode"
    _attr_options = list(HEADWIND_MODE_OPTIONS)

    def __init__(self, coordinator: HeadwindCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_fan_mode"

    @property
    @override
    def current_option(self) -> str | None:
        mode = self.coordinator.data.get("mode")
        if mode is None:
            return None
        return HEADWIND_LABEL_BY_MODE.get(int(mode))

    @override
    async def async_select_option(self, option: str) -> None:
        mode = HEADWIND_MODE_BY_LABEL.get(option)
        if mode is not None:
            await self.coordinator.async_set_mode(mode)

    @property
    @override
    def available(self) -> bool:
        return self.coordinator.connected
