#!/usr/bin/env python3
"""Interactively probe the Sleep/Relax sound track index characteristics.

Unverified in PROTOCOL.md: format is "Integer index", track list not
enumerated, byte width unconfirmed. Writes candidate index values one at
a time (starting with a 1-byte guess, matching every other confirmed
numeric characteristic in this protocol -- if even index 0 gets rejected,
that's a sign the wire format isn't a single byte after all), pausing
for you to listen and describe what's playing, to build up a real track
list and find out whether/where a valid index range ends.

Sound should already be on and audible (with Relax Volume above 0 --
that's the confirmed live volume control, not Sleep Volume; see
PROTOCOL.md) before you disable the HA integration and run this.

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
SLEEP_SOUND_TRACK_UUID = "a54d9906-4298-4656-9bd3-7095e87365d6"
RELAX_SOUND_TRACK_UUID = "0e4fa979-6e76-45f0-8887-762ee399121c"

TRACK_CHARACTERISTICS = {
    "Sleep sound track": SLEEP_SOUND_TRACK_UUID,
    "Relax sound track": RELAX_SOUND_TRACK_UUID,
}

DEFAULT_MAX_INDEX = 9


def dump_properties(client: BleakClient, name: str, uuid: str) -> None:
    char = client.services.get_characteristic(uuid)
    if char is None:
        print(f"{name}: NOT FOUND on this device")
        return
    print(f"{name}: properties={char.properties}")


async def probe_track(
    client: BleakClient, name: str, uuid: str, max_index: int
) -> dict[int, str]:
    print(f"\n=== {name} ({uuid}) ===")
    try:
        original = bytes(await client.read_gatt_char(uuid))
    except Exception as exc:  # noqa: BLE001
        print(f"could not read current value: {exc!r}")
        return {}
    print(f"current raw value: {original!r}")

    log: dict[int, str] = {}
    for index in range(max_index + 1):
        try:
            await client.write_gatt_char(uuid, bytes([index]), response=True)
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

    try:
        await client.write_gatt_char(uuid, original, response=True)
        print(f"restored {name} to {original!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"could not restore {name} to {original!r}: {exc!r}")

    return log


async def main(address: str, max_index: int) -> None:
    async with BleakClient(address) as client:
        try:
            status = await client.read_gatt_char(SOUND_STATUS_UUID)
            print(
                f"Sound status = {status!r} (should be b'\\x01' -- turn "
                "Sound on in HA before disabling the integration if not)"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"could not read sound status: {exc!r}")

        for name, uuid in TRACK_CHARACTERISTICS.items():
            dump_properties(client, name, uuid)

        results: dict[str, dict[int, str]] = {}
        for name, uuid in TRACK_CHARACTERISTICS.items():
            results[name] = await probe_track(client, name, uuid, max_index)

        print("\n=== summary ===")
        for name, log in results.items():
            print(f"\n{name}:")
            if not log:
                print("  (no data)")
            for index, description in log.items():
                print(f"  {index}: {description}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF [max_index]")
        sys.exit(1)
    address = sys.argv[1]
    max_index_arg = int(sys.argv[2]) if len(sys.argv) == 3 else DEFAULT_MAX_INDEX
    asyncio.run(main(address, max_index_arg))
