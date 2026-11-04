"""Sensor entities for the Wahoo Fitness integration."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, override

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODEL_HEADWIND, MODEL_KICKR_BIKE
from .coordinator import KickrBikeCoordinator, WahooFitnessCoordinator
from .entity import WahooFitnessEntity
from .protocol import HEADWIND_MODE_NAMES

PARALLEL_UPDATES = 0


def _value(key: str) -> Callable[[WahooFitnessCoordinator], Any]:
    return lambda coordinator: coordinator.data.get(key)


KICKR_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
    ),
    SensorEntityDescription(
        key="cadence",
        translation_key="cadence",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:pedal-bike",
    ),
    SensorEntityDescription(
        key="speed",
        translation_key="speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    SensorEntityDescription(
        key="front_gear",
        translation_key="front_gear",
        icon="mdi:cog",
    ),
    SensorEntityDescription(
        key="rear_gear",
        translation_key="rear_gear",
        icon="mdi:cog",
    ),
    SensorEntityDescription(
        key="front_gear_count",
        translation_key="front_gear_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cog-outline",
    ),
    SensorEntityDescription(
        key="rear_gear_count",
        translation_key="rear_gear_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cog-outline",
    ),
    SensorEntityDescription(
        key="training_status",
        translation_key="training_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:train",
    ),
)

_KICKR_DATA_KEYS = {
    "power": "power_w",
    "cadence": "cadence_rpm",
    "speed": "speed_kmh",
}

HEADWIND_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="mode",
        translation_key="mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(HEADWIND_MODE_NAMES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:fan",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wahoo Fitness sensors."""
    coordinator: WahooFitnessCoordinator = entry.runtime_data
    if entry.data["model"] == MODEL_KICKR_BIKE:
        entities: list[SensorEntity] = [
            KickrBikeSensor(
                coordinator,
                description,
                _value(_KICKR_DATA_KEYS.get(description.key, description.key)),
            )
            for description in KICKR_SENSORS
        ]
        entities.append(KickrDistanceSensor(coordinator))
        async_add_entities(entities)
    elif entry.data["model"] == MODEL_HEADWIND:
        async_add_entities(
            HeadwindModeSensor(coordinator, description) for description in HEADWIND_SENSORS
        )


class KickrBikeSensor(WahooFitnessEntity, SensorEntity):
    """A KICKR BIKE sensor backed by coordinator data."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: KickrBikeCoordinator,
        description: SensorEntityDescription,
        value_fn: Callable[[WahooFitnessCoordinator], Any],
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"
        self._value_fn = value_fn

    @property
    @override
    def native_value(self) -> Any:
        return self._value_fn(self.coordinator)

    @property
    @override
    def available(self) -> bool:
        return self.coordinator.connected and self.native_value is not None


class KickrDistanceSensor(WahooFitnessEntity, RestoreSensor):
    """Session distance for a KICKR BIKE.

    The bike only reports instantaneous speed, so distance is integrated from
    speed.  The accumulated value is restored across Home Assistant restarts.
    """

    _attr_translation_key = "distance"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, coordinator: KickrBikeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_distance"
        self._distance = 0.0
        self._last_update: float | None = None

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (restored := await self.async_get_last_sensor_data()) is not None:
            try:
                self._distance = float(restored.native_value)
            except (TypeError, ValueError):
                self._distance = 0.0
        self._last_update = time.monotonic()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        now = time.monotonic()
        speed = self.coordinator.data.get("speed_kmh")
        if self._last_update is not None and speed is not None:
            elapsed = now - self._last_update
            # Ignore long gaps (disconnect/restart) rather than inventing miles.
            if 0 < elapsed <= 5:
                self._distance += float(speed) * elapsed / 3600
        self._last_update = now
        super()._handle_coordinator_update()

    @property
    @override
    def native_value(self) -> float:
        return round(self._distance, 4)

    @property
    @override
    def available(self) -> bool:
        return super().available or self._distance > 0


class HeadwindModeSensor(WahooFitnessEntity, SensorEntity):
    """HEADWIND operating mode."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: WahooFitnessCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{description.key}"

    @property
    @override
    def native_value(self) -> str | None:
        mode = self.coordinator.data.get("mode")
        if mode is None:
            return None
        return HEADWIND_MODE_NAMES.get(int(mode))
