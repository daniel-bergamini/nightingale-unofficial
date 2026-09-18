"""Volume and light-level number entities for Nightingale.

All three are 11-step (0-10) level controls, not 0-100 percentages --
despite looking like a percent based on the decompiled app's naming and
byte shape, live testing (binary-searching the write ceiling against a
physical unit) found the device rejects anything above 10 with GATT
Application Error 0x80. See SLEEP_VOLUME_MAX/LIGHT_LEVEL_MAX/
RELAX_VOLUME_MAX in protocol.py and PROTOCOL.md.

Sleep Volume and Relax Volume are kept as separate entities under their
full vendor names rather than assuming one is simply "the" volume: an A/B
listening test found Relax Volume audibly controls live playback while
Sleep Volume's write succeeds with no audible effect, suggesting the
device has two distinct sound profiles (matching PROTOCOL.md's separate,
still-unverified Sleep/Relax sound-track characteristics) rather than one
of the two names just being wrong.

Same read-back-don't-assume architecture as switch.py: initial read on
setup, live notify subscription where the characteristic supports it
(device.py falls back to read/write-only if it doesn't), and a re-read
after every write to reflect what the device actually accepted rather
than the raw value sent.
"""

from __future__ import annotations

import logging

from bleak.exc import BleakError

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightingaleConfigEntry
from .const import MANUFACTURER, MODEL
from .device import NightingaleDevice, NightingaleNotFoundError
from .protocol import (
    LIGHT_LEVEL_MAX,
    LIGHT_LEVEL_UUID,
    RELAX_VOLUME_MAX,
    RELAX_VOLUME_UUID,
    SLEEP_VOLUME_MAX,
    SLEEP_VOLUME_UUID,
    decode_level,
    encode_level,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NightingaleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Nightingale level number entities for a config entry."""
    device = entry.runtime_data
    async_add_entities(
        [
            NightingaleLevelNumber(
                device,
                entry.title,
                SLEEP_VOLUME_UUID,
                SLEEP_VOLUME_MAX,
                "sleep_volume",
                "Sleep Volume",
                "mdi:volume-high",
            ),
            NightingaleLevelNumber(
                device,
                entry.title,
                RELAX_VOLUME_UUID,
                RELAX_VOLUME_MAX,
                "relax_volume",
                "Relax Volume",
                "mdi:volume-medium",
            ),
            NightingaleLevelNumber(
                device,
                entry.title,
                LIGHT_LEVEL_UUID,
                LIGHT_LEVEL_MAX,
                "light_level",
                "Light Level",
                "mdi:brightness-percent",
            ),
        ]
    )


class NightingaleLevelNumber(NumberEntity):
    """A 0..max_value level backed by a single-byte characteristic."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        device: NightingaleDevice,
        room_name: str,
        char_uuid: str,
        max_value: int,
        key: str,
        name: str,
        icon: str,
    ) -> None:
        self._device = device
        self._char_uuid = char_uuid
        self._max_value = max_value
        self._attr_native_max_value = max_value
        self._attr_name = name
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_icon = icon
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            name=room_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_added_to_hass(self) -> None:
        try:
            await self._device.async_start_notify(self._char_uuid, self._handle_notify)
        except (NightingaleNotFoundError, BleakError):
            _LOGGER.debug(
                "%s: could not subscribe to %s", self._device.address, self._char_uuid,
                exc_info=True,
            )
        await self._async_refresh_state()

    async def async_will_remove_from_hass(self) -> None:
        await self._device.async_stop_notify(self._char_uuid, self._handle_notify)

    def _handle_notify(self, data: bytes) -> None:
        self._attr_native_value = decode_level(data)
        self._attr_available = True
        self.async_write_ha_state()

    async def _async_refresh_state(self) -> None:
        try:
            data = await self._device.async_read_gatt(self._char_uuid)
        except (NightingaleNotFoundError, BleakError):
            _LOGGER.warning(
                "%s: could not read %s", self._device.address, self._char_uuid,
                exc_info=True,
            )
            self._attr_available = False
        else:
            self._attr_native_value = decode_level(data)
            self._attr_available = True
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        await self._device.async_write_gatt(
            self._char_uuid, encode_level(round(value), self._max_value)
        )
        await self._async_refresh_state()
