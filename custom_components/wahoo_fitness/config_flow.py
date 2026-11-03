"""Config flow for the Wahoo Fitness integration."""

from __future__ import annotations

import logging
from typing import Any, override

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_MODEL,
    CONF_NAME,
    DOMAIN,
    MODEL_HEADWIND,
    MODEL_KICKR_BIKE,
    MODEL_NAME_PREFIXES,
    MODEL_NAMES,
)

_LOGGER = logging.getLogger(__name__)

VERSION = 1


def _model_for_name(name: str) -> str | None:
    """Return the model for a Bluetooth name, if supported."""
    upper = name.upper()
    for model in (MODEL_KICKR_BIKE, MODEL_HEADWIND):
        if any(upper.startswith(prefix) for prefix in MODEL_NAME_PREFIXES[model]):
            return model
    return None


def _unique_id(model: str, name: str) -> str:
    """Build a stable id from the model and advertised name.

    The advertised BLE address is a random static address and can change when
    the device is power cycled.  The name suffix (e.g. "ABCD") is stable.
    """
    return f"{model}:{name.strip().upper()}"


class WahooFitnessConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Wahoo Fitness device."""

    VERSION = VERSION

    def __init__(self) -> None:
        self._discovered: dict[str, dict[str, Any]] = {}

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device discovered by the Bluetooth integration."""
        name = discovery_info.name or discovery_info.device.name or ""
        model = _model_for_name(name)
        if model is None:
            return self.async_abort(reason="unsupported_device")

        unique_id = _unique_id(model, name)
        await self.async_set_unique_id(unique_id)

        if existing := self._async_current_entry_for_unique_id(unique_id):
            if existing.data.get(CONF_ADDRESS) != discovery_info.address:
                _LOGGER.debug(
                    "Updating address for %s from %s to %s",
                    name,
                    existing.data.get(CONF_ADDRESS),
                    discovery_info.address,
                )
                self.hass.config_entries.async_update_entry(
                    existing,
                    data={**existing.data, CONF_ADDRESS: discovery_info.address},
                )
                self.hass.config_entries.async_schedule_reload(existing.entry_id)
            return self.async_abort(reason="already_configured")

        self._abort_if_unique_id_configured()
        self._discovered[discovery_info.address] = {
            CONF_ADDRESS: discovery_info.address,
            CONF_NAME: name,
            CONF_MODEL: model,
        }
        self.context["title_placeholders"] = {CONF_NAME: name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered device."""
        device = next(iter(self._discovered.values()))
        if user_input is not None:
            return self.async_create_entry(
                title=device[CONF_NAME],
                data=device,
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                CONF_NAME: device[CONF_NAME],
                "address": device[CONF_ADDRESS],
                "model": MODEL_NAMES[device[CONF_MODEL]],
            },
        )

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow started from the UI."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            device = self._discovered.get(address)
            if device is None:
                return self.async_abort(reason="device_not_found")
            await self.async_set_unique_id(_unique_id(device[CONF_MODEL], device[CONF_NAME]))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=device[CONF_NAME],
                data=device,
            )

        configured = {
            entry.unique_id for entry in self._async_current_entries(include_ignore=False)
        }
        options: list[SelectOptionDict] = []
        for info in async_discovered_service_info(self.hass, connectable=True):
            name = info.name or info.device.name or ""
            model = _model_for_name(name)
            if model is None:
                continue
            if _unique_id(model, name) in configured:
                continue
            self._discovered[info.address] = {
                CONF_ADDRESS: info.address,
                CONF_NAME: name,
                CONF_MODEL: model,
            }
            options.append(
                SelectOptionDict(
                    value=info.address,
                    label=f"{name} ({info.address})",
                )
            )

        if not options:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    def _async_current_entry_for_unique_id(self, unique_id: str):
        """Return an existing entry with this unique id, if any."""
        for entry in self._async_current_entries(include_ignore=False):
            if entry.unique_id == unique_id:
                return entry
        return None
