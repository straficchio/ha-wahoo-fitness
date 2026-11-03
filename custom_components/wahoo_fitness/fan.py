"""Fan entity for the Wahoo KICKR HEADWIND."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODEL_HEADWIND
from .coordinator import HeadwindCoordinator
from .entity import WahooFitnessEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data["model"] != MODEL_HEADWIND:
        return
    coordinator: HeadwindCoordinator = entry.runtime_data
    async_add_entities([HeadwindFan(coordinator)])


class HeadwindFan(WahooFitnessEntity, FanEntity):
    """The HEADWIND fan."""

    _attr_name = None
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )
    _attr_speed_count = 100

    def __init__(self, coordinator: HeadwindCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_fan"

    @property
    @override
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("is_on"))

    @property
    @override
    def percentage(self) -> int | None:
        speed = self.coordinator.data.get("speed_pct")
        return None if speed is None else int(speed)

    @override
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self.coordinator.async_turn_on(percentage)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_turn_off()

    @override
    async def async_set_percentage(self, percentage: int) -> None:
        await self.coordinator.async_set_percentage(percentage)

    @property
    @override
    def available(self) -> bool:
        return self.coordinator.connected
