#!/usr/bin/env python3
"""Inspect, and optionally probe, the Sleep/Relax sound track characteristics.

CONFIRMED INCIDENT: an earlier version of this script wrote single-byte
index values (0x00-0x09) into RELAX_SOUND_TRACK_UUID and lost the
original "crickets and tree frog" audio -- because the real value is 2
bytes (b'\\x01\\xfe'), not 1. A recovered-value write via
tools/init_state.py fixed it. See PROTOCOL.md, "Relax Sound Track Is
(At Least) 2 Bytes". Both characteristics are now confirmed 2 bytes on
this unit (sleep b'\\x05\\x00', relax b'\\x01\\xfe').

Because of that, this script is READ-ONLY by default: it just prints
each characteristic's GATT properties and current raw value, so you can
confirm the real byte width before writing anything. Pass --write to
sweep byte 0 through max_index while holding byte 1 fixed at each
characteristic's real original value (setting matching Sound Mode and
volume first, restoring everything after, per the two prior fixes to
this script) -- but know that byte-0-is-the-index is a guess based on
the two known values, not a confirmed format, and the restore write is
not confirmed sufficient by itself (see PROTOCOL.md).

Run this directly against a unit -- NOT through Home Assistant or an
ESPHome proxy. It opens its own BLE connection; disable or reload-off
the Nightingale config entry in HA first, or this will just fail to
connect.

Usage:
    pip install bleak
    python3 track_probe.py AA:BB:CC:DD:EE:FF              # read-only
    python3 track_probe.py AA:BB:CC:DD:EE:FF --write [max_index]
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

    if len(original_track) != 2:
        print(
            f"{name}: original value is {len(original_track)} byte(s), not "
            "the 2 confirmed for sleep/relax sound track on this unit -- "
            "aborting this sweep rather than guessing an unknown format"
        )
        return {}
    fixed_byte = original_track[1]
    print(
        f"holding byte 1 fixed at {fixed_byte:#04x} (from the original "
        "value) and sweeping byte 0 -- this ASSUMES byte 0 is the "
        "meaningful index and byte 1 is something else. That split is a "
        "guess based on the two known values (sleep b'\\x05\\x00', relax "
        "b'\\x01\\xfe'), not a confirmed format."
    )

    await client.write_gatt_char(SOUND_MODE_UUID, bytes([required_mode]), response=True)
    await client.write_gatt_char(volume_uuid, bytes([AUDIBLE_VOLUME]), response=True)
    print(f"set Sound Mode to {required_mode} and {name.split()[0]} volume to {AUDIBLE_VOLUME} for this test")

    log: dict[int, str] = {}
    for index in range(max_index + 1):
        candidate = bytes([index, fixed_byte])
        try:
            await client.write_gatt_char(track_uuid, candidate, response=True)
        except Exception as exc:  # noqa: BLE001
            print(
                f"byte0={index} (full value {candidate!r}): write rejected "
                f"({exc!r}) -- stopping, likely past the valid range"
            )
            break
        description = input(
            f"wrote {candidate!r}. Listen, then describe what's playing "
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


async def main(address: str, do_write: bool, max_index: int) -> None:
    async with BleakClient(address) as client:
        print("--- current raw values (read-only) ---")
        for name, (track_uuid, _mode, _vol) in TRACK_CHARACTERISTICS.items():
            dump_properties(client, name, track_uuid)
            try:
                data = await client.read_gatt_char(track_uuid)
                print(f"{name}: current raw value = {data!r} ({len(data)} byte(s))")
            except Exception as exc:  # noqa: BLE001
                print(f"{name}: could not read current value: {exc!r}")

        if not do_write:
            print("\nRead-only mode (default) -- no writes performed. Pass --write to run the sweep.")
            return

        print(
            "\n--- WRITE MODE: about to sweep byte 0 through "
            f"{max_index} while holding byte 1 fixed at each "
            "characteristic's real original value (both are confirmed 2 "
            "bytes now). The byte-0-is-the-index split is still a guess, "
            "not confirmed. Ctrl+C now to abort. ---"
        )

        try:
            original_sound_status = bytes(await client.read_gatt_char(SOUND_STATUS_UUID))
        except Exception as exc:  # noqa: BLE001
            print(f"could not read sound status: {exc!r}")
            original_sound_status = None
        else:
            print(f"Sound status was {original_sound_status!r}; forcing it on for this test")
            await client.write_gatt_char(SOUND_STATUS_UUID, b"\x01", response=True)

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
            "\nThe automatic restore above wrote back the same bytes read "
            "before this test, which is NOT confirmed sufficient if a "
            "characteristic turns out wider than 1 byte (exactly what "
            "happened to Relax sound track). Check the sound carefully, "
            "and if anything's off, restore via tools/init_state.py rather "
            "than assuming a power cycle alone will fix it this time."
        )


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF [--write [max_index]]")
        sys.exit(1)
    address = args[0]
    do_write = "--write" in args
    rest = [a for a in args[1:] if a != "--write"]
    max_index_arg = int(rest[0]) if rest else DEFAULT_MAX_INDEX
    asyncio.run(main(address, do_write, max_index_arg))
