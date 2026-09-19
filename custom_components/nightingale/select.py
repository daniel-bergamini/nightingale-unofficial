"""Select entities for Nightingale: Sound Mode and sound tracks.

Light Color used to be a 4-preset select here; it's now part of the
full RGB Light entity in light.py instead (see that module's docstring).

The Sleep (Sound Blanket) profile's track is split into two selects --
Room Type and Surface Type -- matching the vendor's own setup wizard
rather than one flat 15-item list; see
_NightingaleBlanketDimensionSelect below.

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
    NATURE_SOUND_TRACKS,
    RELAX_SOUND_TRACK_UUID,
    ROOM_STYLE_LABELS,
    ROOM_TYPE_LABELS,
    SLEEP_SOUND_TRACK_UUID,
    SOUND_MODE_UUID,
    RoomStyle,
    RoomType,
    SoundMode,
    decode_blanket,
    decode_sound_mode,
    decode_sound_track_id,
    encode_blanket,
    encode_sound_mode,
    encode_sound_track_id,
)

_LOGGER = logging.getLogger(__name__)

SOUND_MODE_LABELS = {
    SoundMode.SOUND_BLANKET: "Sound Blanket",
    SoundMode.NATURE_SOUND: "Nature Sound",
}
SOUND_MODE_BY_LABEL = {label: mode for mode, label in SOUND_MODE_LABELS.items()}


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
            NightingaleRelaxSoundTrackSelect(device, entry.title),
            NightingaleSleepRoomTypeSelect(device, entry.title),
            NightingaleSleepSurfaceTypeSelect(device, entry.title),
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


class _NightingaleBlanketDimensionSelect(_NightingaleSelectBase):
    """Shared plumbing for the two Bedroom Blanket dimension selects.

    Matches the vendor's own setup wizard (SelectingBlanketFragment.java):
    a Blanket is chosen from two independent dimensions, Room Type and
    Surface Type, not one flat 15-item list. Both selects read/write the
    same combined SLEEP_SOUND_TRACK_UUID index, so changing one has to
    preserve whatever the other currently is -- async_select_option reads
    the combined value fresh (not cached) before recombining and writing,
    overriding the generic _encode-only pattern the base class assumes.
    """

    def __init__(
        self, device: NightingaleDevice, room_name: str, key: str, name: str, icon: str
    ) -> None:
        super().__init__(device, room_name, SLEEP_SOUND_TRACK_UUID, key, name, icon)

    def _label_for(self, room_type: RoomType, room_style: RoomStyle) -> str:
        raise NotImplementedError

    def _apply(
        self, option: str, room_type: RoomType, room_style: RoomStyle
    ) -> tuple[RoomType, RoomStyle]:
        raise NotImplementedError

    def _decode(self, data: bytes) -> str | None:
        components = decode_blanket(data)
        if components is None:
            return None
        return self._label_for(*components)

    async def async_select_option(self, option: str) -> None:
        try:
            current_raw = await self._device.async_read_gatt(self._char_uuid)
        except (NightingaleNotFoundError, BleakError, TimeoutError):
            _LOGGER.warning(
                "%s: could not read %s before recombining -- defaulting the "
                "other dimension to Adult Bedroom/Absorptive",
                self._device.address,
                self._char_uuid,
                exc_info=True,
            )
            components = None
        else:
            components = decode_blanket(current_raw)
        room_type, room_style = components or (RoomType.BEDROOM, RoomStyle.ABSORPTIVE)
        room_type, room_style = self._apply(option, room_type, room_style)
        await self._device.async_write_gatt(
            self._char_uuid, encode_blanket(room_type, room_style)
        )
        await self._async_refresh_state()


class NightingaleSleepRoomTypeSelect(_NightingaleBlanketDimensionSelect):
    """Room Type half of the Sleep (Sound Blanket) profile selection.

    Only takes effect while Sound Mode is Sound Blanket -- see
    PROTOCOL.md.
    """

    _attr_options = list(ROOM_TYPE_LABELS.values())

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device, room_name, "sleep_room_type", "Sleep Blanket Room Type", "mdi:bed"
        )

    def _label_for(self, room_type: RoomType, room_style: RoomStyle) -> str:
        return ROOM_TYPE_LABELS[room_type]

    def _apply(
        self, option: str, room_type: RoomType, room_style: RoomStyle
    ) -> tuple[RoomType, RoomStyle]:
        new_type = next(rt for rt, label in ROOM_TYPE_LABELS.items() if label == option)
        return new_type, room_style


class NightingaleSleepSurfaceTypeSelect(_NightingaleBlanketDimensionSelect):
    """Surface Type half of the Sleep (Sound Blanket) profile selection.

    Only takes effect while Sound Mode is Sound Blanket -- see
    PROTOCOL.md.
    """

    _attr_options = list(ROOM_STYLE_LABELS.values())

    def __init__(self, device: NightingaleDevice, room_name: str) -> None:
        super().__init__(
            device,
            room_name,
            "sleep_surface_type",
            "Sleep Blanket Surface Type",
            "mdi:texture-box",
        )

    def _label_for(self, room_type: RoomType, room_style: RoomStyle) -> str:
        return ROOM_STYLE_LABELS[room_style]

    def _apply(
        self, option: str, room_type: RoomType, room_style: RoomStyle
    ) -> tuple[RoomType, RoomStyle]:
        new_style = next(rs for rs, label in ROOM_STYLE_LABELS.items() if label == option)
        return room_type, new_style
