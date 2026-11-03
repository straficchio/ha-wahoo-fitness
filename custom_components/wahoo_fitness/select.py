"""Select entity for the KICKR BIKE control mode."""

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
    MODEL_KICKR_BIKE,
)
from .coordinator import KickrBikeCoordinator
from .entity import WahooFitnessEntity

PARALLEL_UPDATES = 1

CONTROL_MODE_DESCRIPTION = SelectEntityDescription(
    key="control_mode",
    translation_key="control_mode",
    icon="mdi:bike",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data["model"] != MODEL_KICKR_BIKE:
        return
    coordinator: KickrBikeCoordinator = entry.runtime_data
    async_add_entities([KickrControlModeSelect(coordinator, CONTROL_MODE_DESCRIPTION)])


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
