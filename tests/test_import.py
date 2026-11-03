"""Smoke tests that the integration imports under Home Assistant."""

from __future__ import annotations


def test_integration_imports() -> None:
    from custom_components.wahoo_fitness import (
        async_setup_entry,  # noqa: F401
        config_flow,
        fan,
        number,
        select,
        sensor,
    )
    from custom_components.wahoo_fitness.coordinator import (
        HeadwindCoordinator,
        KickrBikeCoordinator,
    )

    assert config_flow.WahooFitnessConfigFlow.__name__ == "WahooFitnessConfigFlow"
    assert HeadwindCoordinator is not None
    assert KickrBikeCoordinator is not None
    assert fan.HeadwindFan is not None
    assert number.KickrTargetPowerNumber is not None
    assert select.KickrControlModeSelect is not None
    assert sensor.KickrDistanceSensor is not None
