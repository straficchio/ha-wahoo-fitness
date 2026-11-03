"""Shared test fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "wahoo_fitness"))
sys.path.insert(0, str(ROOT))

pytest_plugins = "pytest_homeassistant_custom_component"

# The test helper installs its own ``custom_components`` package from its
# testing_config.  Extend its search path with the repository's integrations.
import custom_components  # noqa: E402

if str(ROOT / "custom_components") not in custom_components.__path__:
    custom_components.__path__.append(str(ROOT / "custom_components"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield
