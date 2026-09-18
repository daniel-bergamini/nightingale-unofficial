#!/usr/bin/env python3
"""Interactive A/B test: which volume characteristic actually gain-controls
whatever the unit is currently playing?

PROTOCOL.md already documents that this vendor's characteristic *names*
aren't trustworthy -- "SoundOn"/"SoundOff" turned out to be schedule
setters, not the power toggle. So "Sleep Volume" actually controlling
live playback loudness, just because of its name, isn't a safe
assumption. This writes a quiet value then a loud value to each
candidate, pausing for you to listen and answer each time, and prints a
summary at the end.

Run this directly against a unit -- NOT through Home Assistant or an
ESPHome proxy. It opens its own BLE connection; disable or reload-off
the Nightingale config entry in HA first, or this will just fail to
connect. Sound should already be on (via HA, before you disable the
integration) so there's something playing to listen to.

Usage:
    pip install bleak
    python3 volume_ab_probe.py AA:BB:CC:DD:EE:FF
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient

SOUND_STATUS_UUID = "cc339aad-1847-42ed-a606-3e0a9b3bfca5"
SLEEP_VOLUME_UUID = "6dd68afc-9d26-4e67-95cb-c56c784360e7"
RELAX_VOLUME_UUID = "bb23ae19-b2f0-46f4-930d-d89047d92c06"

CANDIDATES = {
    "Sleep volume": SLEEP_VOLUME_UUID,
    "Relax volume": RELAX_VOLUME_UUID,
}

# Sleep volume's ceiling is confirmed 10; Relax volume's is unverified, so
# this tries progressively smaller values until one is actually accepted.
LOUD_CANDIDATES = (10, 8, 5, 3, 1)


async def find_loud_value(client: BleakClient, uuid: str) -> int | None:
    for value in LOUD_CANDIDATES:
        try:
            await client.write_gatt_char(uuid, bytes([value]), response=True)
        except Exception:  # noqa: BLE001
            continue
        return value
    return None


async def test_characteristic(client: BleakClient, name: str, uuid: str) -> str:
    print(f"\n=== {name} ({uuid}) ===")
    try:
        original = (await client.read_gatt_char(uuid))[0]
    except Exception as exc:  # noqa: BLE001
        print(f"could not read current value: {exc!r}")
        return "read failed"
    print(f"current value: {original}")

    loud = await find_loud_value(client, uuid)
    if loud is None:
        print("could not write any nonzero value at all -- write may not be supported")
        return "write failed"

    input(f"Set {name} to 0 (quiet). Press Enter when ready to listen...")
    await client.write_gatt_char(uuid, bytes([0]), response=True)
    quiet_answer = input("Any change in volume? (y/n): ")

    input(f"Now setting {name} to {loud} (loud). Press Enter when ready to listen...")
    await client.write_gatt_char(uuid, bytes([loud]), response=True)
    loud_answer = input("Any change in volume? (y/n): ")

    try:
        await client.write_gatt_char(uuid, bytes([original]), response=True)
        print(f"restored {name} to {original}")
    except Exception as exc:  # noqa: BLE001
        print(f"could not restore {name} to {original}: {exc!r}")

    heard_change = (
        quiet_answer.strip().lower().startswith("y")
        or loud_answer.strip().lower().startswith("y")
    )
    return "AUDIBLE CHANGE" if heard_change else "no audible change"


async def main(address: str) -> None:
    async with BleakClient(address) as client:
        try:
            status = await client.read_gatt_char(SOUND_STATUS_UUID)
            print(f"Sound status = {status!r} (should be \\x01 -- if not, turn Sound on in HA before disabling the integration and rerunning)")
        except Exception as exc:  # noqa: BLE001
            print(f"could not read sound status: {exc!r}")

        results = {}
        for name, uuid in CANDIDATES.items():
            results[name] = await test_characteristic(client, name, uuid)

        print("\n=== summary ===")
        for name, result in results.items():
            print(f"{name:15s} {result}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
