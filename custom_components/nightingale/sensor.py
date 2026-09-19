"""Sensor entities for Nightingale.

Room Name / Location Name are the device's own self-reported strings,
set once during onboarding in the vendor app -- read-only here, and
distinct from the room name you type into this integration's own
config flow (which only labels the HA device and is never written back
to the unit). Marked diagnostic since they're informational, not
something you'd act on day to day.

Now Playing isn't a single stored value on the device -- it's derived
from four separate characteristics (Sound status, Sound Mode, and
whichever of Relax/Sleep sound track is live for the current mode),
the same way the app's own Room.getCurrentPlayingString() combines
them. The exact wording is our own, not a quote of the app's: its
R.string format text wasn't available in this decompile (no
strings.xml), only the logic that picks which value to show.
"""

from __future__ import annotations

import logging

from bleak.exc import BleakError

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightingaleConfigEntry
from .const import MANUFACTURER, MODEL
from .device import NightingaleDevice, NightingaleNotFoundError
from .protocol import (
    LOCATION_NAME_UUID,
    NATURE_SOUND_TRACKS,
    RELAX_SOUND_TRACK_UUID,
    ROOM_NAME_UUID,
    ROOM_STYLE_LABELS,
    ROOM_TYPE_LABELS,
    SLEEP_SOUND_TRACK_UUID,
    SOUND_MODE_UUID,
    SOUND_STATUS_UUID,
    SoundMode,
    decode_blanket,
    decode_bool,
    decode_sound_mode,
    decode_sound_track_id,
    decode_string,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NightingaleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Nightingale sensor entities for a config entry."""
    device = entry.runtime_data
    async_add_entities(
        [
            NightingaleRoomNameSensor(device, entry.title),
            NightingaleLocationNameSensor(device, entry.title),
            NightingaleNowPlayingSensor(device, entry.title),
        ]
    )


class _NightingaleStringSensor(SensorEntity):
    """A read-only UTF-8 string characteristic."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        self._attr_native_value = decode_string(data)
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
            self._attr_native_value = decode_string(data)
            self._attr_available = True
        self.async_write_ha_state()


class NightingaleRoomNameSensor(_NightingaleStringSensor):
    """The unit's own self-reported room name."""

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device, room_name, ROOM_NAME_UUID, "device_room_name", "Device Room Name", "mdi:tag-text"
        )


class NightingaleLocationNameSensor(_NightingaleStringSensor):
    """The unit's own self-reported location name."""

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device,
            room_name,
            LOCATION_NAME_UUID,
            "device_location_name",
            "Device Location Name",
            "mdi:map-marker",
        )


class NightingaleNowPlayingSensor(SensorEntity):
    """A single computed summary of what's actually playing right now.

    Mirrors the app's Room.getCurrentPlayingString(): Sound off -> "Off";
    Sound on and Sound Mode is Nature Sound -> the Relax Sound Track
    name; Sound on and Sound Mode is Sound Blanket -> the Sleep Blanket's
    combined Room Type/Surface Type name.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Now Playing"

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_now_playing"
        self._attr_icon = "mdi:music-note"
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            name=room_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        self._sound_on: bool | None = None
        self._sound_mode: SoundMode | None = None
        self._relax_track: str | None = None
        self._sleep_blanket_label: str | None = None

    async def async_added_to_hass(self) -> None:
        for uuid, handler in (
            (SOUND_STATUS_UUID, self._handle_sound_status),
            (SOUND_MODE_UUID, self._handle_sound_mode),
            (RELAX_SOUND_TRACK_UUID, self._handle_relax_track),
            (SLEEP_SOUND_TRACK_UUID, self._handle_sleep_blanket),
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
        await self._device.async_stop_notify(SOUND_STATUS_UUID, self._handle_sound_status)
        await self._device.async_stop_notify(SOUND_MODE_UUID, self._handle_sound_mode)
        await self._device.async_stop_notify(
            RELAX_SOUND_TRACK_UUID, self._handle_relax_track
        )
        await self._device.async_stop_notify(
            SLEEP_SOUND_TRACK_UUID, self._handle_sleep_blanket
        )

    def _handle_sound_status(self, data: bytes) -> None:
        self._sound_on = decode_bool(data)
        self._recompute()

    def _handle_sound_mode(self, data: bytes) -> None:
        self._sound_mode = decode_sound_mode(data)
        self._recompute()

    def _handle_relax_track(self, data: bytes) -> None:
        self._relax_track = self._relax_track_label(data)
        self._recompute()

    def _handle_sleep_blanket(self, data: bytes) -> None:
        self._sleep_blanket_label = self._blanket_label(data)
        self._recompute()

    @staticmethod
    def _relax_track_label(data: bytes) -> str | None:
        sound_index = decode_sound_track_id(data)
        for label, index in NATURE_SOUND_TRACKS.items():
            if index == sound_index:
                return label
        return None

    @staticmethod
    def _blanket_label(data: bytes) -> str | None:
        components = decode_blanket(data)
        if components is None:
            return None
        room_type, room_style = components
        return f"{ROOM_TYPE_LABELS[room_type]} Blanket ({ROOM_STYLE_LABELS[room_style]})"

    async def _async_refresh_all(self) -> None:
        try:
            status_data = await self._device.async_read_gatt(SOUND_STATUS_UUID)
            mode_data = await self._device.async_read_gatt(SOUND_MODE_UUID)
            relax_data = await self._device.async_read_gatt(RELAX_SOUND_TRACK_UUID)
            sleep_data = await self._device.async_read_gatt(SLEEP_SOUND_TRACK_UUID)
        except (NightingaleNotFoundError, BleakError, TimeoutError):
            _LOGGER.warning(
                "%s: could not read state for Now Playing", self._device.address,
                exc_info=True,
            )
            self._attr_available = False
            self.async_write_ha_state()
            return
        self._sound_on = decode_bool(status_data)
        self._sound_mode = decode_sound_mode(mode_data)
        self._relax_track = self._relax_track_label(relax_data)
        self._sleep_blanket_label = self._blanket_label(sleep_data)
        self._attr_available = True
        self._recompute()

    def _recompute(self) -> None:
        if self._sound_on is None or self._sound_mode is None:
            return
        if not self._sound_on:
            self._attr_native_value = "Off"
        elif self._sound_mode is SoundMode.NATURE_SOUND:
            self._attr_native_value = self._relax_track or "Nature Sound (unknown track)"
        else:
            self._attr_native_value = self._sleep_blanket_label or "Sound Blanket (unknown)"
        self.async_write_ha_state()
