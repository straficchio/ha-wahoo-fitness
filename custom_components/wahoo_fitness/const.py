"""Constants for the Wahoo Fitness integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "wahoo_fitness"
MANUFACTURER: Final = "Wahoo Fitness"

CONF_MODEL: Final = "model"
CONF_NAME: Final = "name"
CONF_ADDRESS: Final = "address"

MODEL_KICKR_BIKE: Final = "kickr_bike"
MODEL_HEADWIND: Final = "headwind"

MODEL_NAMES: Final[dict[str, str]] = {
    MODEL_KICKR_BIKE: "KICKR BIKE",
    MODEL_HEADWIND: "KICKR HEADWIND",
}

MODEL_NAME_PREFIXES: Final[dict[str, tuple[str, ...]]] = {
    MODEL_KICKR_BIKE: ("KICKR BIKE",),
    MODEL_HEADWIND: ("HEADWIND", "KICKR HEADWIND"),
}

# Reconnect/watchdog tuning
CONNECT_TIMEOUT: Final = 25.0
RECONNECT_DELAY: Final = 5.0
DATA_WATCHDOG: Final = 12.0
CONTROL_RETRY_INTERVAL: Final = 30.0
PUSH_INTERVAL: Final = 1.0

# KICKR BIKE limits
MAX_TARGET_POWER: Final = 2000
MIN_GRADE: Final = -15.0
MAX_GRADE: Final = 20.0

# Control modes exposed by the select entity
MODE_OFF: Final = "off"
MODE_ERG: Final = "erg"
MODE_SIMULATION: Final = "simulation"
CONTROL_MODES: Final[dict[str, str]] = {
    MODE_OFF: "Off",
    MODE_ERG: "ERG (target power)",
    MODE_SIMULATION: "Simulation (grade)",
}
CONTROL_MODE_BY_LABEL: Final[dict[str, str]] = {
    label: mode for mode, label in CONTROL_MODES.items()
}
