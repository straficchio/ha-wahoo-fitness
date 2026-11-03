"""Config flow tests for the Wahoo Fitness integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wahoo_fitness.const import DOMAIN


def _discovery(name: str, address: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        address=address,
        device=SimpleNamespace(name=name),
    )


async def test_bluetooth_discovery(hass) -> None:
    """A KICKR BIKE advertisement creates a config entry."""
    info = _discovery("KICKR BIKE ABCD", "AA:BB:CC:DD:EE:FF")

    with (
        patch(
            "custom_components.wahoo_fitness.coordinator.async_ble_device_from_address",
            return_value=None,
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "bluetooth"},
            data=info,
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == "KICKR BIKE ABCD"
    assert entry.unique_id == "kickr_bike:KICKR BIKE ABCD"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data == {
        "address": "AA:BB:CC:DD:EE:FF",
        "name": "KICKR BIKE ABCD",
        "model": "kickr_bike",
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_bluetooth_discovery_headwind(hass) -> None:
    """A HEADWIND advertisement creates a fan config entry."""
    info = _discovery("HEADWIND 1234", "11:22:33:44:55:66")

    with (
        patch(
            "custom_components.wahoo_fitness.coordinator.async_ble_device_from_address",
            return_value=None,
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "bluetooth"},
            data=info,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.unique_id == "headwind:HEADWIND 1234"
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_user_flow_lists_devices(hass) -> None:
    """The user flow offers discovered devices."""
    infos = [
        _discovery("KICKR BIKE ABCD", "AA:BB:CC:DD:EE:FF"),
        _discovery("HEADWIND 1234", "11:22:33:44:55:66"),
    ]

    with (
        patch(
            "custom_components.wahoo_fitness.config_flow.async_discovered_service_info",
            return_value=infos,
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.async_ble_device_from_address",
            return_value=None,
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"address": "11:22:33:44:55:66"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.unique_id == "headwind:HEADWIND 1234"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_address_change_updates_entry(hass) -> None:
    """A rediscovered device with a new random address updates the entry."""
    first = _discovery("HEADWIND 1234", "11:22:33:44:55:66")
    second = _discovery("HEADWIND 1234", "22:33:44:55:66:77")

    with (
        patch(
            "custom_components.wahoo_fitness.coordinator.async_ble_device_from_address",
            return_value=None,
        ),
        patch(
            "custom_components.wahoo_fitness.coordinator.async_register_callback",
            return_value=lambda: None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "bluetooth"}, data=first
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
        entry = result["result"]
        await hass.async_block_till_done()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "bluetooth"}, data=second
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert entry is not None
    assert entry.data["address"] == "22:33:44:55:66:77"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
