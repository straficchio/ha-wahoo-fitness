"""Number entities for controlling a Wahoo KICKR BIKE."""

from __future__ import annotations

from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_GRADE, MAX_TARGET_POWER, MIN_GRADE, MODEL_KICKR_BIKE
from .coordinator import KickrBikeCoordinator
from .entity import WahooFitnessEntity

PARALLEL_UPDATES = 1

TARGET_POWER_DESCRIPTION = NumberEntityDescription(
    key="target_power",
    translation_key="target_power",
    native_min_value=0,
    native_max_value=MAX_TARGET_POWER,
    native_step=1,
    native_unit_of_measurement=UnitOfPower.WATT,
    device_class=NumberDeviceClass.POWER,
    mode=NumberMode.SLIDER,
    icon="mdi:lightning-bolt",
)

GRADE_DESCRIPTION = NumberEntityDescription(
    key="grade",
    translation_key="grade",
    native_min_value=MIN_GRADE,
    native_max_value=MAX_GRADE,
    native_step=0.5,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.SLIDER,
    icon="mdi:slope-uphill",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data["model"] != MODEL_KICKR_BIKE:
        return
    coordinator: KickrBikeCoordinator = entry.runtime_data
    async_add_entities(
        [
            KickrTargetPowerNumber(coordinator, TARGET_POWER_DESCRIPTION),
            KickrGradeNumber(coordinator, GRADE_DESCRIPTION),
        ]
    )


class KickrNumberBase(WahooFitnessEntity, NumberEntity):
    """Base number entity for KICKR BIKE controls."""

    entity_description: NumberEntityDescription

    def __init__(
        self,
        coordinator: KickrBikeCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"

    @property
    @override
    def available(self) -> bool:
        return self.coordinator.connected


class KickrTargetPowerNumber(KickrNumberBase):
    """ERG target power."""

    @property
    @override
    def native_value(self) -> float | None:
        value = self.coordinator.data.get("target_power_w")
        return None if value is None else float(value)

    @override
    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_target_power(value)


class KickrGradeNumber(KickrNumberBase):
    """Simulated grade."""

    @property
    @override
    def native_value(self) -> float | None:
        value = self.coordinator.data.get("target_grade_pct")
        return None if value is None else float(value)

    @override
    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_grade(value)
