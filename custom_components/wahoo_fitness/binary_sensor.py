"""Binary sensors for the Wahoo Fitness integration."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODEL_KICKR_BIKE
from .coordinator import WahooFitnessCoordinator
from .entity import WahooFitnessEntity

PARALLEL_UPDATES = 0

CONNECTED_DESCRIPTION = BinarySensorEntityDescription(
    key="connected",
    translation_key="connected",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)

PEDALING_DESCRIPTION = BinarySensorEntityDescription(
    key="pedaling",
    translation_key="pedaling",
    device_class=BinarySensorDeviceClass.RUNNING,
    icon="mdi:bike-fast",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WahooFitnessCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [WahooConnectedSensor(coordinator, CONNECTED_DESCRIPTION)]
    if entry.data["model"] == MODEL_KICKR_BIKE:
        entities.append(KickrPedalingSensor(coordinator, PEDALING_DESCRIPTION))
    async_add_entities(entities)


class WahooConnectedSensor(WahooFitnessEntity, BinarySensorEntity):
    """Connection state of the BLE device."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: WahooFitnessCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"

    @property
    @override
    def is_on(self) -> bool:
        return self.coordinator.connected

    @property
    @override
    def available(self) -> bool:
        return True


class KickrPedalingSensor(WahooFitnessEntity, BinarySensorEntity):
    """Whether the rider is turning the cranks."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: WahooFitnessCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"

    @property
    @override
    def is_on(self) -> bool:
        power = self.coordinator.data.get("power_w") or 0
        cadence = self.coordinator.data.get("cadence_rpm") or 0
        return power > 0 or cadence > 0

    @property
    @override
    def available(self) -> bool:
        return self.coordinator.connected
