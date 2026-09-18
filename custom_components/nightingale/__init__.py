"""The Nightingale integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .device import NightingaleDevice, NightingaleNotFoundError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.NUMBER, Platform.SELECT]

# Nothing about entity setup (each platform's async_setup_entry, which
# calls async_added_to_hass on every entity) is individually guaranteed
# to finish quickly, even with device.py's own per-operation timeouts --
# a stuck config entry ("Initializing" forever) has happened more than
# once from a single entity's setup hanging. This is the actual backstop:
# no matter what specific thing misbehaves in the future, entity setup
# either finishes or gets cut off and reported as ConfigEntryNotReady
# (which HA retries with its own backoff) within this bound.
ENTITY_SETUP_TIMEOUT = 60

type NightingaleConfigEntry = ConfigEntry[NightingaleDevice]


async def async_setup_entry(hass: HomeAssistant, entry: NightingaleConfigEntry) -> bool:
    """Set up a Nightingale unit from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    device = NightingaleDevice(hass, address)

    try:
        await device.async_connect()
    except NightingaleNotFoundError as err:
        raise ConfigEntryNotReady(
            f"{address} not seen by any Bluetooth adapter or proxy"
        ) from err
    except Exception as err:  # bleak_retry_connector's BleakError subclasses
        raise ConfigEntryNotReady(f"Could not connect to {address}: {err}") from err

    entry.runtime_data = device

    try:
        async with asyncio.timeout(ENTITY_SETUP_TIMEOUT):
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except TimeoutError as err:
        await device.async_disconnect()
        raise ConfigEntryNotReady(
            f"Setting up entities for {address} took longer than "
            f"{ENTITY_SETUP_TIMEOUT}s"
        ) from err

    entry.async_on_unload(device.async_disconnect)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NightingaleConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
