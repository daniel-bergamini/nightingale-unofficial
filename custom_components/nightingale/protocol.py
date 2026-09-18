"""Nightingale BLE protocol codec.

Pure encode/decode helpers — no I/O, no bleak imports. Byte formats are
documented in PROTOCOL.md at the repo root; that file is the source of
truth for every UUID and format listed here.

Only "confirmed" characteristics (traced to a byte-construction call site
in the decompiled app, and/or live-tested) get first-class encode/decode
helpers below. "Unverified" UUIDs are still defined as constants — so
device.py/entities can reference them once confirmed — but are kept out
of the entity-facing codec functions until someone traces or live-tests
them. See UNVERIFIED_NOTES at the bottom for the specific list.
"""

from __future__ import annotations

from enum import IntEnum

# ---------------------------------------------------------------------------
# Primary service
# ---------------------------------------------------------------------------

SERVICE_UUID = "80b03553-ac03-41bc-8d3c-931f0a330168"

# ---------------------------------------------------------------------------
# Confirmed characteristics
# ---------------------------------------------------------------------------

# Power / status (immediate on/off — NOT the "SoundOn"/"SoundOff"/"LightOn"/
# "LightOff" characteristics, which are schedule time setters; see
# PROTOCOL.md "Notes on Schedule vs. Immediate Control").
SOUND_STATUS_UUID = "cc339aad-1847-42ed-a606-3e0a9b3bfca5"
LIGHT_STATUS_UUID = "6e31cc36-4901-432f-aed1-cc5f87009853"
SOUND_MUTE_UUID = "74ba593d-506d-435e-becf-dc84069f24f8"

# Sound
SOUND_MODE_UUID = "1eb5c56d-5970-4294-9208-f16d66c396ef"
SLEEP_VOLUME_UUID = "6dd68afc-9d26-4e67-95cb-c56c784360e7"
# Live-tested (binary search on a physical unit): the device rejects any
# with-response write above 10 with GATT Application Error 0x80. This is
# an 11-step level (0-10), NOT a 0-100 percentage as originally inferred
# from the decompiled app's naming/shape alone -- see PROTOCOL.md.
SLEEP_VOLUME_MAX = 10
# Live A/B tested against a physical unit (2026-09-18): unlike Sleep
# Volume, this one audibly changes whatever's currently playing -- despite
# the vendor's own naming, THIS is the live volume control, not Sleep
# Volume. Sleep Volume's write succeeds with no audible effect; its real
# purpose is still unknown, so both are kept as separate entities under
# their full vendor names rather than assuming one is simply "the" volume.
# The 0-10 ceiling itself is carried over from Sleep Volume/Light Level's
# independently binary-searched value, not separately binary-searched for
# this characteristic -- a reasonable bet, not a confirmed measurement.
RELAX_VOLUME_UUID = "bb23ae19-b2f0-46f4-930d-d89047d92c06"
RELAX_VOLUME_MAX = 10
# Confirmed via decompiled construction code (Room.java's NatureSound
# setup) and cross-checked live: wire format is a big-endian 16-bit
# integer matching NatureSound.soundIndex exactly. The recovered original
# value b'\x01\xfe' = 0x01FE = 510 = "Lakeshore" -- which fits what was
# actually heard (crickets, and a knocking sound more likely a frog than
# a bird) far better than assuming that byte pair was a plain 0-9 index.
RELAX_SOUND_TRACK_UUID = "0e4fa979-6e76-45f0-8887-762ee399121c"
NATURE_SOUND_TRACKS: dict[str, int] = {
    "Lakeshore": 510,
    "Crickets": 520,
    "Loons": 530,
    "Whale Songs": 540,
    "Rainstorm": 550,
}
SOUND_AUTO_ON_UUID = "11104650-14be-436b-a900-b72763c3be82"
SOUND_AUTO_OFF_UUID = "5e6379e1-bd5b-44a2-ac16-74f845d6c388"

# Light
LIGHT_LEVEL_UUID = "adfa5e07-ebe3-4362-ae05-b63cc5aad5b1"
# Same live-tested 0-10 ceiling as SLEEP_VOLUME_MAX, confirmed independently.
LIGHT_LEVEL_MAX = 10
LIGHT_COLOR_UUID = "4bf0b1b1-aadc-47aa-b5fb-c7f9affa2462"
LIGHT_AUTO_ON_UUID = "0eef9fab-7878-4e33-9201-f9029a342530"
LIGHT_AUTO_OFF_UUID = "36d5794c-091d-4e3e-8146-af0477e240a7"

# Device / misc (strings, confirmed by naming + format, low risk if wrong)
ROOM_NAME_UUID = "add88f42-6127-41e7-8f0e-de054d99d91d"
LOCATION_NAME_UUID = "37c4cabf-3f32-40ef-8ee3-92db35671faa"

# ---------------------------------------------------------------------------
# Unverified characteristics — DO NOT wire into entities without live
# confirmation (either traced to construction code, or tested against a
# physical unit). Kept here only so device.py/entities have a single place
# to reference the UUID once confirmed.
# ---------------------------------------------------------------------------

# PAGE_VOLUME_UUID intentionally omitted: ngVolumePageUUID in the
# decompiled NightingaleGatt.java is itself
# UUID.fromString("f2e85c5e6-97a4-4c3a-9742-5278bf3881ec") — 9 hex digits
# in the first group, not a valid UUID. This is a genuine vendor bug (that
# call would throw IllegalArgumentException), not a transcription error,
# so this characteristic is unusable and unimplementable as shipped. See
# PROTOCOL.md "Known Vendor Bug: Page Volume UUID".
VOLUME_BALANCE_UUID = "c32f5045-d621-4c9e-8f9b-557b5a5d65cd"
# Confirmed 2 bytes live (original value b'\x05\x00'), but unlike
# RELAX_SOUND_TRACK_UUID, the corresponding BedroomBlanket ID scheme
# isn't traced yet -- 0x0500 = 1280 big-endian doesn't match anything
# known. Stays unverified until that's found.
SLEEP_SOUND_TRACK_UUID = "a54d9906-4298-4656-9bd3-7095e87365d6"
SOUND_SCHEDULED_UUID = "86dcd724-031d-4ebe-a2e1-912670a06c3c"
LIGHT_SCHEDULED_UUID = "8ae4953e-0db8-11e6-a148-3e1d05defe78"
DISABLE_BUTTON_UUID = "b686b17d-b0dd-4415-bb76-895745d9d5ed"
RAMP_UUID = "7c54068a-46a7-42c9-a318-f5d47f492028"
FLASH_INDICATOR_UUID = "370ffb49-7626-4531-8b22-dbdeb359a304"
LEGACY_ON_OFF_UUID = "c7d62e9d-c352-43b5-a00a-939254cfb3ca"  # not wired to anything in the app; do not use

UNVERIFIED_NOTES = {
    VOLUME_BALANCE_UUID: "format guessed as signed integer L/R skew, not traced/tested",
    SLEEP_SOUND_TRACK_UUID: "confirmed 2-byte big-endian format, but the BedroomBlanket id list isn't traced yet -- do not guess valid values",
    SOUND_SCHEDULED_UUID: "guessed 0x00/0x01 enable flag, not traced/tested",
    LIGHT_SCHEDULED_UUID: "guessed 0x00/0x01 enable flag, not traced/tested",
    DISABLE_BUTTON_UUID: "format entirely unknown",
    RAMP_UUID: "format entirely unknown",
    FLASH_INDICATOR_UUID: "format entirely unknown",
    LEGACY_ON_OFF_UUID: "not wired to any method in the decompiled app; likely vestigial, do not use as power toggle",
}


class SoundMode(IntEnum):
    """Sound mode enum ordinal, per PROTOCOL.md."""

    SOUND_BLANKET = 0x00
    NATURE_SOUND = 0x01


# Named RGB presets confirmed (or inferred) in PROTOCOL.md. "Red" is
# inferred, not confirmed against a physical unit.
LIGHT_COLOR_PRESETS: dict[str, tuple[int, int, int]] = {
    "white": (0xFF, 0xFF, 0xFF),
    "green": (0x00, 0xFF, 0x00),
    "blue": (0x00, 0x00, 0xFF),
    "red": (0xFF, 0x00, 0x00),  # inferred, not confirmed live
}


def encode_bool(value: bool) -> bytes:
    """Encode a 1-byte 0x00/0x01 flag (status, mute)."""
    return bytes([0x01 if value else 0x00])


def decode_bool(data: bytes) -> bool:
    """Decode a 1-byte 0x00/0x01 flag."""
    return data[0] != 0x00


def encode_level(value: int, max_value: int) -> bytes:
    """Encode a 1-byte level in 0..max_value.

    `max_value` is the device's actual live-tested ceiling for this
    specific characteristic (e.g. SLEEP_VOLUME_MAX), not necessarily 100
    -- see the module-level comments by each *_MAX constant. It's a
    required argument rather than a default specifically so a call site
    can't silently assume 100 the way protocol.py itself once did.
    """
    if not 0 <= value <= max_value:
        raise ValueError(f"value out of range 0-{max_value}: {value}")
    return bytes([value])


def decode_level(data: bytes) -> int:
    """Decode a 1-byte level. Valid range depends on the characteristic."""
    return data[0]


def encode_sound_mode(mode: SoundMode) -> bytes:
    """Encode the sound mode enum ordinal."""
    return bytes([int(mode)])


def decode_sound_mode(data: bytes) -> SoundMode:
    """Decode the sound mode enum ordinal."""
    return SoundMode(data[0])


def encode_rgb(red: int, green: int, blue: int) -> bytes:
    """Encode a 3-byte RGB light color."""
    for name, value in (("red", red), ("green", green), ("blue", blue)):
        if not 0 <= value <= 255:
            raise ValueError(f"{name} channel out of range 0-255: {value}")
    return bytes([red, green, blue])


def decode_rgb(data: bytes) -> tuple[int, int, int]:
    """Decode a 3-byte RGB light color."""
    return (data[0], data[1], data[2])


def encode_nature_sound_track(sound_index: int) -> bytes:
    """Encode a Nature Sound track selection (RELAX_SOUND_TRACK_UUID).

    Big-endian 16-bit, matching the decompiled app's NatureSound.soundIndex
    field exactly. Use NATURE_SOUND_TRACKS for the confirmed name->index
    map rather than passing an arbitrary integer.
    """
    return sound_index.to_bytes(2, "big")


def decode_nature_sound_track(data: bytes) -> int:
    """Decode a Nature Sound track selection. Returns the raw soundIndex."""
    return int.from_bytes(data, "big")


def encode_schedule_time(hour: int, minute: int) -> bytes:
    """Encode a schedule time pair. Wire format is [minute, hour]."""
    if not 0 <= hour <= 23:
        raise ValueError(f"hour out of range 0-23: {hour}")
    if not 0 <= minute <= 59:
        raise ValueError(f"minute out of range 0-59: {minute}")
    return bytes([minute, hour])


def decode_schedule_time(data: bytes) -> tuple[int, int]:
    """Decode a schedule time pair. Returns (hour, minute)."""
    minute, hour = data[0], data[1]
    return (hour, minute)
