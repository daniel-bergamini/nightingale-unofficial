"""Schedule time entities for Nightingale.

These are the "SoundOn"/"SoundOff"/"LightOn"/"LightOff" characteristics
-- confirmed [minute, hour] pairs, and NOT the immediate power toggles
despite the names (see PROTOCOL.md, "Notes on Schedule vs. Immediate
Control"). The corresponding enable flags (Sound/Light Auto-Schedule)
are already switches in switch.py; these are the actual times those
flags gate. Whether a saved time here does anything depends entirely on
its matching Auto-Schedule switch being on.

Same read-back-don't-assume architecture as the other platforms: initial
read on setup, live notify subscription where the characteristic
supports it, and a re-read after every write.
"""

from __future__ import annotations

import logging
from datetime import time as dt_time

from bleak.exc import BleakError

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightingaleConfigEntry
from .const import MANUFACTURER, MODEL
from .device import NightingaleDevice, NightingaleNotFoundError
from .protocol import (
    LIGHT_AUTO_OFF_UUID,
    LIGHT_AUTO_ON_UUID,
    SOUND_AUTO_OFF_UUID,
    SOUND_AUTO_ON_UUID,
    decode_schedule_time,
    encode_schedule_time,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NightingaleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Nightingale schedule time entities for a config entry."""
    device = entry.runtime_data
    async_add_entities(
        [
            NightingaleScheduleTime(
                device,
                entry.title,
                SOUND_AUTO_ON_UUID,
                "sound_auto_on_time",
                "Sound Auto-On Time",
                "mdi:volume-high",
            ),
            NightingaleScheduleTime(
                device,
                entry.title,
                SOUND_AUTO_OFF_UUID,
                "sound_auto_off_time",
                "Sound Auto-Off Time",
                "mdi:volume-off",
            ),
            NightingaleScheduleTime(
                device,
                entry.title,
                LIGHT_AUTO_ON_UUID,
                "light_auto_on_time",
                "Light Auto-On Time",
                "mdi:lightbulb-on",
            ),
            NightingaleScheduleTime(
                device,
                entry.title,
                LIGHT_AUTO_OFF_UUID,
                "light_auto_off_time",
                "Light Auto-Off Time",
                "mdi:lightbulb-off",
            ),
        ]
    )


class NightingaleScheduleTime(TimeEntity):
    """A [minute, hour] schedule time -- see module docstring."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        device: NightingaleDevice,
        room_name: str,
        char_uuid: str,
        key: str,
        name: str,
        icon: str,
    ) -> None:
        self._device = device
        self._char_uuid = char_uuid
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
        except (NightingaleNotFoundError, BleakError, TimeoutError):
            _LOGGER.debug(
                "%s: could not subscribe to %s", self._device.address, self._char_uuid,
                exc_info=True,
            )
        await self._async_refresh_state()

    async def async_will_remove_from_hass(self) -> None:
        await self._device.async_stop_notify(self._char_uuid, self._handle_notify)

    def _handle_notify(self, data: bytes) -> None:
        hour, minute = decode_schedule_time(data)
        self._attr_native_value = dt_time(hour=hour, minute=minute)
        self._attr_available = True
        self.async_write_ha_state()

    async def _async_refresh_state(self) -> None:
        try:
            data = await self._device.async_read_gatt(self._char_uuid)
        except (NightingaleNotFoundError, BleakError, TimeoutError):
            _LOGGER.warning(
                "%s: could not read %s", self._device.address, self._char_uuid,
                exc_info=True,
            )
            self._attr_available = False
        else:
            hour, minute = decode_schedule_time(data)
            self._attr_native_value = dt_time(hour=hour, minute=minute)
            self._attr_available = True
        self.async_write_ha_state()

    async def async_set_value(self, value: dt_time) -> None:
        await self._device.async_write_gatt(
            self._char_uuid, encode_schedule_time(value.hour, value.minute)
        )
        await self._async_refresh_state()
