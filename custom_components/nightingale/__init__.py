"""The Nightingale integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_COPY_SETTINGS_FROM, DOMAIN
from .device import NightingaleDevice, NightingaleNotFoundError
from .sync import async_copy_settings

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.TIME,
]

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

    if copy_from_address := entry.data.get(CONF_COPY_SETTINGS_FROM):
        await _async_copy_settings_once(hass, entry, device, copy_from_address)

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


async def _async_copy_settings_once(
    hass: HomeAssistant,
    entry: NightingaleConfigEntry,
    target_device: NightingaleDevice,
    source_address: str,
) -> None:
    """Run the settings copy chosen during config flow (see sync.py and
    config_flow.py's "copy_settings" step), then remove the marker from
    entry.data so it never runs again on a later reload/restart -- it's
    a one-time clone, same as the vendor app's own add-a-second-unit
    behavior, not an ongoing sync.
    """
    source_entry = next(
        (
            candidate
            for candidate in hass.config_entries.async_entries(DOMAIN)
            if candidate.entry_id != entry.entry_id
            and candidate.data.get(CONF_ADDRESS) == source_address
        ),
        None,
    )
    source_device = getattr(source_entry, "runtime_data", None) if source_entry else None
    if source_device is None:
        _LOGGER.warning(
            "Could not copy settings from %s to %s: source entry not currently loaded",
            source_address,
            target_device.address,
        )
    else:
        _LOGGER.info(
            "Copying settings from %s to %s", source_address, target_device.address
        )
        results = await async_copy_settings(source_device, target_device)
        failed = [uuid for uuid, status in results.items() if status != "ok"]
        if failed:
            _LOGGER.warning(
                "Copying settings from %s to %s: %d of %d characteristics failed: %s",
                source_address,
                target_device.address,
                len(failed),
                len(results),
                failed,
            )

    new_data = dict(entry.data)
    new_data.pop(CONF_COPY_SETTINGS_FROM, None)
    hass.config_entries.async_update_entry(entry, data=new_data)


async def async_unload_entry(hass: HomeAssistant, entry: NightingaleConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
