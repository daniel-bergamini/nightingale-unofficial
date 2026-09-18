#!/usr/bin/env python3
"""Interactively probe the Sleep/Relax sound track index characteristics.

Unverified in PROTOCOL.md: format is "Integer index", track list not
enumerated, byte width unconfirmed. Writes candidate index values one at
a time (starting with a 1-byte guess, matching every other confirmed
numeric characteristic in this protocol -- if even index 0 gets rejected,
that's a sign the wire format isn't a single byte after all), pausing
for you to listen and describe what's playing, to build up a real track
list and find out whether/where a valid index range ends.

Each profile only produces sound when its own volume is nonzero *and*
Sound Mode is actually set to that profile (Sleep Volume is live only
under Sound Blanket, Relax Volume only under Nature Sound -- see
PROTOCOL.md). A first version of this script skipped that setup, so a
"silent" result may have just meant "wrong mode/volume," not "this
index doesn't work." This version sets the matching Sound Mode and an
audible volume for each profile before testing its track indices, and
restores everything (mode, both volumes, both track values, and Sound
status itself) afterward. It also force-enables Sound status at the
start rather than just checking it -- an earlier version only warned if
Sound looked off instead of turning it on, so a run with Sound
forgotten off produced "all silence" for reasons having nothing to do
with track indices.

IMPORTANT: that restore writes back the same bytes it read before the
test started, but live testing found this isn't always enough to
actually restore the original *sound* -- a run that cycled through
Relax sound track indices left the unit playing something other than
its original crickets/bird loop even after writing that original byte
back, because the track selection apparently lives in volatile
state that a byte write-back doesn't fully reset. A full power cycle
(unplug, wait ~10s, plug back in) fixed it. **Power-cycle the unit
after running this script, every time** -- don't rely on the
automatic restore alone.

Run this directly against a unit -- NOT through Home Assistant or an
ESPHome proxy. It opens its own BLE connection; disable or reload-off
the Nightingale config entry in HA first, or this will just fail to
connect.

Usage:
    pip install bleak
    python3 track_probe.py AA:BB:CC:DD:EE:FF [max_index]
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient

SOUND_STATUS_UUID = "cc339aad-1847-42ed-a606-3e0a9b3bfca5"
SOUND_MODE_UUID = "1eb5c56d-5970-4294-9208-f16d66c396ef"
SLEEP_VOLUME_UUID = "6dd68afc-9d26-4e67-95cb-c56c784360e7"
RELAX_VOLUME_UUID = "bb23ae19-b2f0-46f4-930d-d89047d92c06"
SLEEP_SOUND_TRACK_UUID = "a54d9906-4298-4656-9bd3-7095e87365d6"
RELAX_SOUND_TRACK_UUID = "0e4fa979-6e76-45f0-8887-762ee399121c"

SOUND_BLANKET = 0x00
NATURE_SOUND = 0x01

AUDIBLE_VOLUME = 8  # confirmed 0-10 range; loud but not maxed out

# name -> (track uuid, required sound mode, matching volume uuid)
TRACK_CHARACTERISTICS = {
    "Sleep sound track": (SLEEP_SOUND_TRACK_UUID, SOUND_BLANKET, SLEEP_VOLUME_UUID),
    "Relax sound track": (RELAX_SOUND_TRACK_UUID, NATURE_SOUND, RELAX_VOLUME_UUID),
}

DEFAULT_MAX_INDEX = 9


def dump_properties(client: BleakClient, name: str, uuid: str) -> None:
    char = client.services.get_characteristic(uuid)
    if char is None:
        print(f"{name}: NOT FOUND on this device")
        return
    print(f"{name}: properties={char.properties}")


async def probe_track(
    client: BleakClient,
    name: str,
    track_uuid: str,
    required_mode: int,
    volume_uuid: str,
    max_index: int,
) -> dict[int, str]:
    print(f"\n=== {name} ({track_uuid}) ===")
    try:
        original_track = bytes(await client.read_gatt_char(track_uuid))
        original_mode = bytes(await client.read_gatt_char(SOUND_MODE_UUID))
        original_volume = bytes(await client.read_gatt_char(volume_uuid))
    except Exception as exc:  # noqa: BLE001
        print(f"could not read current state: {exc!r}")
        return {}
    print(f"current raw track value: {original_track!r}")

    await client.write_gatt_char(SOUND_MODE_UUID, bytes([required_mode]), response=True)
    await client.write_gatt_char(volume_uuid, bytes([AUDIBLE_VOLUME]), response=True)
    print(f"set Sound Mode to {required_mode} and {name.split()[0]} volume to {AUDIBLE_VOLUME} for this test")

    log: dict[int, str] = {}
    for index in range(max_index + 1):
        try:
            await client.write_gatt_char(track_uuid, bytes([index]), response=True)
        except Exception as exc:  # noqa: BLE001
            print(
                f"index {index}: write rejected ({exc!r}) -- stopping, "
                "likely past the valid range (or the wire format isn't "
                "a single byte, if this happened at index 0)"
            )
            break
        description = input(
            f"index {index} written. Listen, then describe what's playing "
            f"(or 'same', 'silence', or Enter to skip): "
        ).strip()
        log[index] = description or "(no description given)"

    for uuid, original in (
        (track_uuid, original_track),
        (SOUND_MODE_UUID, original_mode),
        (volume_uuid, original_volume),
    ):
        try:
            await client.write_gatt_char(uuid, original, response=True)
        except Exception as exc:  # noqa: BLE001
            print(f"could not restore {uuid} to {original!r}: {exc!r}")
    print(f"restored {name}, Sound Mode, and its volume to their original values")

    return log


async def main(address: str, max_index: int) -> None:
    async with BleakClient(address) as client:
        try:
            original_sound_status = bytes(await client.read_gatt_char(SOUND_STATUS_UUID))
        except Exception as exc:  # noqa: BLE001
            print(f"could not read sound status: {exc!r}")
            original_sound_status = None
        else:
            print(f"Sound status was {original_sound_status!r}; forcing it on for this test")
            await client.write_gatt_char(SOUND_STATUS_UUID, b"\x01", response=True)

        for name, (track_uuid, _mode, _vol) in TRACK_CHARACTERISTICS.items():
            dump_properties(client, name, track_uuid)

        results: dict[str, dict[int, str]] = {}
        for name, (track_uuid, mode, vol_uuid) in TRACK_CHARACTERISTICS.items():
            results[name] = await probe_track(
                client, name, track_uuid, mode, vol_uuid, max_index
            )

        if original_sound_status is not None:
            try:
                await client.write_gatt_char(
                    SOUND_STATUS_UUID, original_sound_status, response=True
                )
                print(f"restored Sound status to {original_sound_status!r}")
            except Exception as exc:  # noqa: BLE001
                print(f"could not restore Sound status to {original_sound_status!r}: {exc!r}")

        print("\n=== summary ===")
        for name, log in results.items():
            print(f"\n{name}:")
            if not log:
                print("  (no data)")
            for index, description in log.items():
                print(f"  {index}: {description}")

        print(
            "\nPower-cycle the unit now (unplug ~10s, plug back in). The "
            "automatic restore above writes back the same bytes read before "
            "this test, but that isn't always enough to restore the actual "
            "original sound -- track selection appears to hold volatile "
            "state a byte write-back doesn't fully reset."
        )


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF [max_index]")
        sys.exit(1)
    address = sys.argv[1]
    max_index_arg = int(sys.argv[2]) if len(sys.argv) == 3 else DEFAULT_MAX_INDEX
    asyncio.run(main(address, max_index_arg))
