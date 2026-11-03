"""Base entity for the Wahoo Fitness integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import WahooFitnessCoordinator


class WahooFitnessEntity(CoordinatorEntity[WahooFitnessCoordinator]):
    """Base class for Wahoo Fitness entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WahooFitnessCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device registry information."""
        return self.coordinator.device_info

    @property
    def available(self) -> bool:
        """Return whether the device is connected."""
        return self.coordinator.connected
