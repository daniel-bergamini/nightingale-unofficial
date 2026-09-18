"""Power switches for Nightingale — sound and light, via the Status characteristics.

Deliberately NOT built on the "SoundOn"/"SoundOff"/"LightOn"/"LightOff"
characteristics — see PROTOCOL.md. Those set auto-schedule times, not the
immediate on/off state.

State is read back from the device (initial read on setup, then live
notify) rather than assumed from the last command written, so the entity
reflects reality if the unit is toggled by its physical button or drifts
for any other reason.
"""

from __future__ import annotations

import logging
from typing import Any

from bleak.exc import BleakError

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightingaleConfigEntry
from .const import MANUFACTURER, MODEL
from .device import NightingaleDevice, NightingaleNotFoundError
from .protocol import LIGHT_STATUS_UUID, SOUND_STATUS_UUID, decode_bool, encode_bool

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NightingaleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Nightingale power switches for a config entry."""
    device = entry.runtime_data
    async_add_entities(
        [
            NightingalePowerSwitch(
                device, entry.title, SOUND_STATUS_UUID, "sound_power", "Sound"
            ),
            NightingalePowerSwitch(
                device, entry.title, LIGHT_STATUS_UUID, "light_power", "Light"
            ),
        ]
    )


class NightingalePowerSwitch(SwitchEntity):
    """An immediate on/off toggle backed by one of the Status characteristics."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        device: NightingaleDevice,
        room_name: str,
        char_uuid: str,
        key: str,
        name: str,
    ) -> None:
        self._device = device
        self._char_uuid = char_uuid
        self._attr_name = name
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            name=room_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_added_to_hass(self) -> None:
        await self._device.async_start_notify(self._char_uuid, self._handle_notify)
        await self._async_refresh_state()

    async def async_will_remove_from_hass(self) -> None:
        await self._device.async_stop_notify(self._char_uuid, self._handle_notify)

    def _handle_notify(self, data: bytes) -> None:
        self._attr_is_on = decode_bool(data)
        self._attr_available = True
        self.async_write_ha_state()

    async def _async_refresh_state(self) -> None:
        try:
            data = await self._device.async_read_gatt(self._char_uuid)
        except (NightingaleNotFoundError, BleakError):
            _LOGGER.debug(
                "%s: could not read %s", self._device.address, self._char_uuid,
                exc_info=True,
            )
            self._attr_available = False
        else:
            self._attr_is_on = decode_bool(data)
            self._attr_available = True
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._device.async_write_gatt(self._char_uuid, encode_bool(True))
        await self._async_refresh_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.async_write_gatt(self._char_uuid, encode_bool(False))
        await self._async_refresh_state()
