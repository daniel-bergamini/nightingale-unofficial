"""Sound mode and light color select entities for Nightingale.

Same read-back-don't-assume architecture as switch.py/number.py: initial
read on setup, live notify subscription where the characteristic
supports it, and a re-read after every write.
"""

from __future__ import annotations

import logging

from bleak.exc import BleakError

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NightingaleConfigEntry
from .const import MANUFACTURER, MODEL
from .device import NightingaleDevice, NightingaleNotFoundError
from .protocol import (
    BEDROOM_BLANKETS,
    LIGHT_COLOR_PRESETS,
    LIGHT_COLOR_UUID,
    NATURE_SOUND_TRACKS,
    RELAX_SOUND_TRACK_UUID,
    SLEEP_SOUND_TRACK_UUID,
    SOUND_MODE_UUID,
    SoundMode,
    decode_rgb,
    decode_sound_mode,
    decode_sound_track_id,
    encode_rgb,
    encode_sound_mode,
    encode_sound_track_id,
)

_LOGGER = logging.getLogger(__name__)

SOUND_MODE_LABELS = {
    SoundMode.SOUND_BLANKET: "Sound Blanket",
    SoundMode.NATURE_SOUND: "Nature Sound",
}
SOUND_MODE_BY_LABEL = {label: mode for mode, label in SOUND_MODE_LABELS.items()}

# name.capitalize() turns "white" into "White", etc.
LIGHT_COLOR_LABELS = {rgb: name.capitalize() for name, rgb in LIGHT_COLOR_PRESETS.items()}
LIGHT_COLOR_RGB_BY_LABEL = {label: rgb for rgb, label in LIGHT_COLOR_LABELS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NightingaleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Nightingale select entities for a config entry."""
    device = entry.runtime_data
    async_add_entities(
        [
            NightingaleSoundModeSelect(device, entry.title),
            NightingaleLightColorSelect(device, entry.title),
            NightingaleRelaxSoundTrackSelect(device, entry.title),
            NightingaleSleepSoundTrackSelect(device, entry.title),
        ]
    )


class _NightingaleSelectBase(SelectEntity):
    """Shared read-back plumbing; subclasses supply the codec."""

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

    def _decode(self, data: bytes) -> str | None:
        raise NotImplementedError

    def _encode(self, option: str) -> bytes:
        raise NotImplementedError

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
        self._attr_current_option = self._decode(data)
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
            self._attr_current_option = self._decode(data)
            self._attr_available = True
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        await self._device.async_write_gatt(self._char_uuid, self._encode(option))
        await self._async_refresh_state()


class NightingaleSoundModeSelect(_NightingaleSelectBase):
    """Sound Blanket vs Nature Sound."""

    _attr_options = list(SOUND_MODE_LABELS.values())

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device, room_name, SOUND_MODE_UUID, "sound_mode", "Sound Mode", "mdi:waveform"
        )

    def _decode(self, data: bytes) -> str | None:
        return SOUND_MODE_LABELS.get(decode_sound_mode(data))

    def _encode(self, option: str) -> bytes:
        return encode_sound_mode(SOUND_MODE_BY_LABEL[option])


class NightingaleLightColorSelect(_NightingaleSelectBase):
    """Light color, from the confirmed/inferred RGB presets in protocol.py.

    "Red" is inferred, not confirmed against a physical unit -- see
    PROTOCOL.md. If the device is set to some other RGB value entirely
    (e.g. from before this integration existed), current_option comes
    back None: HA shows the select as unset until you explicitly pick one
    of the known presets.
    """

    _attr_options = list(LIGHT_COLOR_RGB_BY_LABEL.keys())

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device, room_name, LIGHT_COLOR_UUID, "light_color", "Light Color", "mdi:palette"
        )

    def _decode(self, data: bytes) -> str | None:
        return LIGHT_COLOR_LABELS.get(decode_rgb(data))

    def _encode(self, option: str) -> bytes:
        return encode_rgb(*LIGHT_COLOR_RGB_BY_LABEL[option])


class _NightingaleSoundTrackSelect(_NightingaleSelectBase):
    """Shared codec for the two sound-track selects.

    Both RELAX_SOUND_TRACK_UUID and SLEEP_SOUND_TRACK_UUID share the same
    big-endian 16-bit soundIndex wire format (confirmed via decompiled
    construction code: Room.java's NatureSound setup for Relax,
    Blanket.java's index arithmetic for Sleep) -- they just draw from
    different name->index maps with different valid ranges.
    """

    def __init__(
        self,
        device: NightingaleDevice,
        room_name: str,
        char_uuid: str,
        key: str,
        name: str,
        icon: str,
        track_by_label: dict[str, int],
    ) -> None:
        super().__init__(device, room_name, char_uuid, key, name, icon)
        self._track_by_label = track_by_label

    def _decode(self, data: bytes) -> str | None:
        sound_index = decode_sound_track_id(data)
        for label, index in self._track_by_label.items():
            if index == sound_index:
                return label
        return None

    def _encode(self, option: str) -> bytes:
        return encode_sound_track_id(self._track_by_label[option])


class NightingaleRelaxSoundTrackSelect(_NightingaleSoundTrackSelect):
    """Which Nature Sound plays under the Relax profile.

    Only audible while Sound Mode is Nature Sound -- see PROTOCOL.md.
    If the device is set to some value outside NATURE_SOUND_TRACKS,
    current_option comes back None rather than guessing.
    """

    _attr_options = list(NATURE_SOUND_TRACKS.keys())

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device,
            room_name,
            RELAX_SOUND_TRACK_UUID,
            "relax_sound_track",
            "Relax Sound Track",
            "mdi:pine-tree",
            NATURE_SOUND_TRACKS,
        )


class NightingaleSleepSoundTrackSelect(_NightingaleSoundTrackSelect):
    """Which Bedroom Blanket plays under the Sleep profile.

    Only audible while Sound Mode is Sound Blanket -- see PROTOCOL.md.
    The 15 values are 3 room styles (Absorptive/Neutral/Reflective) x 5
    room types (Adult Bedroom/Kids/Snoring/Tinnitus/Hospital), confirmed
    via decompiled construction code (Blanket.java). If the device is
    set to some value outside BEDROOM_BLANKETS -- e.g. the leftover
    non-functional value from before this was traced -- current_option
    comes back None rather than guessing.
    """

    _attr_options = list(BEDROOM_BLANKETS.keys())

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device,
            room_name,
            SLEEP_SOUND_TRACK_UUID,
            "sleep_sound_track",
            "Sleep Sound Track",
            "mdi:bed",
            BEDROOM_BLANKETS,
        )
