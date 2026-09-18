"""The Nightingale integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .device import NightingaleDevice, NightingaleNotFoundError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.NUMBER]

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(device.async_disconnect)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NightingaleConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
