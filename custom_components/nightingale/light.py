"""Light entity for Nightingale: on/off, brightness, and full RGB color.

Replaces what used to be three separate entities (the "Light" switch,
the "Light Level" number, and the "Light Color" preset select) with a
single native HA `light`, matching how HA users actually expect a light
to work: one entity with a brightness slider and a color wheel, not
three unrelated controls. Nothing about the underlying protocol changed
-- this is still three independent characteristics (LIGHT_STATUS_UUID,
LIGHT_LEVEL_UUID, LIGHT_COLOR_UUID) read and written separately, just
presented as one entity.

The device only accepts arbitrary RGB on the wire (confirmed live, see
PROTOCOL.md "Confirmed: Light Color Is Exactly 4 Colors" and the
live-RGB-test follow-up) -- the app's own 4-color limit was a pure UI
choice, not a device constraint. That's what makes a real color wheel
possible here at all. Some blends (notably warm/orange tones, a large
red component alongside a moderate-to-large green component) don't
render faithfully due to what's most likely an uncorrected RGB LED --
see PROTOCOL.md for the full writeup. Not something this integration
can fix in software: the device reports back exactly the RGB value it
was sent, so there's nothing to read that indicates miscalibration, and
guessing a correction curve from a handful of photos isn't reliable
enough to ship.

Brightness is presented on HA's standard 0-255 scale and scaled to/from
the device's native 0-10 level (see LIGHT_LEVEL_MAX in protocol.py) --
same reasoning as number.py's level entities, just converted at the
edge instead of exposed raw, since HA's color wheel UI assumes a
0-255 brightness is available whenever RGB color is.

Same read-back-don't-assume architecture as the other platforms:
initial read on setup, live notify subscription where the
characteristic supports it, and a re-read after every write.
"""

from __future__ import annotations

import logging
from typing import Any

from bleak.exc import BleakError

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightingaleConfigEntry
from .const import MANUFACTURER, MODEL
from .device import NightingaleDevice, NightingaleNotFoundError
from .protocol import (
    LIGHT_COLOR_UUID,
    LIGHT_LEVEL_MAX,
    LIGHT_LEVEL_UUID,
    LIGHT_STATUS_UUID,
    decode_bool,
    decode_level,
    decode_rgb,
    encode_bool,
    encode_level,
    encode_rgb,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NightingaleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Nightingale light entity for a config entry."""
    device = entry.runtime_data
    async_add_entities([NightingaleLight(device, entry.title)])


def _level_to_brightness(level: int) -> int:
    return round(level * 255 / LIGHT_LEVEL_MAX)


def _brightness_to_level(brightness: int) -> int:
    return round(brightness * LIGHT_LEVEL_MAX / 255)


class NightingaleLight(LightEntity):
    """The unit's light: on/off, brightness, and RGB color."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Light"
    _attr_icon = "mdi:lightbulb"
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_light"
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            name=room_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_added_to_hass(self) -> None:
        for uuid, handler in (
            (LIGHT_STATUS_UUID, self._handle_status_notify),
            (LIGHT_LEVEL_UUID, self._handle_level_notify),
            (LIGHT_COLOR_UUID, self._handle_color_notify),
        ):
            try:
                await self._device.async_start_notify(uuid, handler)
            except (NightingaleNotFoundError, BleakError, TimeoutError):
                _LOGGER.debug(
                    "%s: could not subscribe to %s", self._device.address, uuid,
                    exc_info=True,
                )
        await self._async_refresh_all()

    async def async_will_remove_from_hass(self) -> None:
        await self._device.async_stop_notify(LIGHT_STATUS_UUID, self._handle_status_notify)
        await self._device.async_stop_notify(LIGHT_LEVEL_UUID, self._handle_level_notify)
        await self._device.async_stop_notify(LIGHT_COLOR_UUID, self._handle_color_notify)

    def _handle_status_notify(self, data: bytes) -> None:
        self._attr_is_on = decode_bool(data)
        self._attr_available = True
        self.async_write_ha_state()

    def _handle_level_notify(self, data: bytes) -> None:
        self._attr_brightness = _level_to_brightness(decode_level(data))
        self._attr_available = True
        self.async_write_ha_state()

    def _handle_color_notify(self, data: bytes) -> None:
        self._attr_rgb_color = decode_rgb(data)
        self._attr_available = True
        self.async_write_ha_state()

    async def _async_refresh_all(self) -> None:
        try:
            status_data = await self._device.async_read_gatt(LIGHT_STATUS_UUID)
            level_data = await self._device.async_read_gatt(LIGHT_LEVEL_UUID)
            color_data = await self._device.async_read_gatt(LIGHT_COLOR_UUID)
        except (NightingaleNotFoundError, BleakError, TimeoutError):
            _LOGGER.warning(
                "%s: could not read light state", self._device.address, exc_info=True
            )
            self._attr_available = False
            self.async_write_ha_state()
            return
        self._attr_is_on = decode_bool(status_data)
        self._attr_brightness = _level_to_brightness(decode_level(level_data))
        self._attr_rgb_color = decode_rgb(color_data)
        self._attr_available = True
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._device.async_write_gatt(LIGHT_STATUS_UUID, encode_bool(True))
        if ATTR_BRIGHTNESS in kwargs:
            level = _brightness_to_level(kwargs[ATTR_BRIGHTNESS])
            await self._device.async_write_gatt(
                LIGHT_LEVEL_UUID, encode_level(level, LIGHT_LEVEL_MAX)
            )
        if ATTR_RGB_COLOR in kwargs:
            await self._device.async_write_gatt(
                LIGHT_COLOR_UUID, encode_rgb(*kwargs[ATTR_RGB_COLOR])
            )
        await self._async_refresh_all()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.async_write_gatt(LIGHT_STATUS_UUID, encode_bool(False))
        await self._async_refresh_all()
