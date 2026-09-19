"""Copy settings from one Nightingale unit to another.

Mirrors the vendor app's own LeDeviceSync.syncDevices(): triggered once,
when adding a second unit to a room that already has one, cloning a
fixed list of characteristics from the existing ("master") unit onto
the new one. Not an ongoing sync -- runs exactly once, during the new
entry's first setup, same as the app only ever runs it from the
add-a-device wizard.

Deliberately does a raw byte passthrough (read from source, write the
same bytes to target) rather than decode-then-re-encode through
protocol.py -- this is what the app itself does (it moves the raw
byte[] it read straight into the write operation, no decoding), and it
means a bug in some characteristic's codec can't corrupt a copy that
never needed the codec in the first place.
"""

from __future__ import annotations

import logging

from bleak.exc import BleakError

from .device import NightingaleDevice, NightingaleNotFoundError
from .protocol import (
    LIGHT_AUTO_OFF_UUID,
    LIGHT_AUTO_ON_UUID,
    LIGHT_COLOR_UUID,
    LIGHT_LEVEL_UUID,
    LIGHT_SCHEDULED_UUID,
    LIGHT_STATUS_UUID,
    LOCATION_NAME_UUID,
    RELAX_SOUND_TRACK_UUID,
    RELAX_VOLUME_UUID,
    ROOM_NAME_UUID,
    SLEEP_SOUND_TRACK_UUID,
    SLEEP_VOLUME_UUID,
    SOUND_AUTO_OFF_UUID,
    SOUND_AUTO_ON_UUID,
    SOUND_MODE_UUID,
    SOUND_MUTE_UUID,
    SOUND_SCHEDULED_UUID,
    SOUND_STATUS_UUID,
)

_LOGGER = logging.getLogger(__name__)

# Same 18 characteristics LeDeviceSync.syncDevices() copies, in the same
# order. Notably absent, same as the app: Volume Balance (L/R skew is
# specific to a unit's physical placement, not something that should
# transfer), Disable Button, Ramp -- the app doesn't sync these either.
SYNC_CHARACTERISTICS: tuple[str, ...] = (
    LOCATION_NAME_UUID,
    ROOM_NAME_UUID,
    SLEEP_SOUND_TRACK_UUID,
    SOUND_STATUS_UUID,
    LIGHT_STATUS_UUID,
    SOUND_MUTE_UUID,
    SLEEP_VOLUME_UUID,
    LIGHT_LEVEL_UUID,
    SOUND_SCHEDULED_UUID,
    LIGHT_SCHEDULED_UUID,
    LIGHT_COLOR_UUID,
    SOUND_AUTO_ON_UUID,
    SOUND_AUTO_OFF_UUID,
    LIGHT_AUTO_ON_UUID,
    LIGHT_AUTO_OFF_UUID,
    SOUND_MODE_UUID,
    RELAX_SOUND_TRACK_UUID,
    RELAX_VOLUME_UUID,
)


async def async_copy_settings(
    source: NightingaleDevice, target: NightingaleDevice
) -> dict[str, str]:
    """Copy every SYNC_CHARACTERISTICS value from source to target.

    Best-effort: one characteristic failing doesn't stop the rest.
    Returns a UUID -> "ok"/"failed: ..." map for logging/diagnostics.
    """
    results: dict[str, str] = {}
    for char_uuid in SYNC_CHARACTERISTICS:
        try:
            data = await source.async_read_gatt(char_uuid)
            await target.async_write_gatt(char_uuid, data)
        except (NightingaleNotFoundError, BleakError, TimeoutError) as exc:
            _LOGGER.warning(
                "Copying %s from %s to %s failed: %r",
                char_uuid,
                source.address,
                target.address,
                exc,
            )
            results[char_uuid] = f"failed: {exc!r}"
        else:
            results[char_uuid] = "ok"
    return results
