#!/usr/bin/env python3
"""Diagnose GATT write failures against a physical Nightingale unit directly.

First run against a real unit found Sleep Volume / Light Level rejecting
`with-response` writes above some threshold with "Application Error 0x80",
while accepting small values fine -- a real ceiling below 100, not a
state/permission issue. It also showed that `write-without-response`
reports "OK" even for values the firmware silently drops, since that mode
gets no ATT-level confirmation -- so only `with-response` results are a
trustworthy pass/fail signal. This version binary-searches for the exact
accepted ceiling using `with-response` writes only, and restores each
characteristic's original value afterward.

Run this directly against a unit -- NOT through Home Assistant or an
ESPHome proxy. It opens its own BLE connection; most BLE peripherals only
accept one central connection at a time, so disable or reload-off the
Nightingale config entry in HA first, or this will just fail to connect.

Usage:
    pip install bleak
    python3 gatt_probe.py AA:BB:CC:DD:EE:FF
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient

SOUND_STATUS_UUID = "cc339aad-1847-42ed-a606-3e0a9b3bfca5"
LIGHT_STATUS_UUID = "6e31cc36-4901-432f-aed1-cc5f87009853"
SLEEP_VOLUME_UUID = "6dd68afc-9d26-4e67-95cb-c56c784360e7"
LIGHT_LEVEL_UUID = "adfa5e07-ebe3-4362-ae05-b63cc5aad5b1"

CHARACTERISTICS = {
    "Sound status": SOUND_STATUS_UUID,
    "Light status": LIGHT_STATUS_UUID,
    "Sleep volume": SLEEP_VOLUME_UUID,
    "Light level": LIGHT_LEVEL_UUID,
}

# Characteristics to binary-search a write ceiling for, with a value already
# confirmed to succeed (from the first probe run) to anchor the low end.
RANGE_TARGETS = {
    "Sleep volume": (SLEEP_VOLUME_UUID, 8),
    "Light level": (LIGHT_LEVEL_UUID, 8),
}


async def dump_properties(client: BleakClient) -> None:
    print("\n--- GATT properties (from the device's own service table) ---")
    for name, uuid in CHARACTERISTICS.items():
        char = client.services.get_characteristic(uuid)
        if char is None:
            print(f"{name:15s} {uuid}  NOT FOUND on this device")
            continue
        print(f"{name:15s} {uuid}  properties={char.properties}")


async def dump_values(client: BleakClient, label: str) -> None:
    print(f"\n--- current values ({label}) ---")
    for name, uuid in CHARACTERISTICS.items():
        try:
            data = await client.read_gatt_char(uuid)
            print(f"{name:15s} = {data!r}")
        except Exception as exc:  # noqa: BLE001 - diagnostic tool, want to see everything
            print(f"{name:15s} read failed: {exc!r}")


async def safe_read_byte(client: BleakClient, uuid: str, default: int) -> int:
    try:
        return (await client.read_gatt_char(uuid))[0]
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not read {uuid} to compute a nudge value ({exc!r}); defaulting to {default}")
        return default


async def accepts(client: BleakClient, uuid: str, value: int) -> bool:
    try:
        await client.write_gatt_char(uuid, bytes([value]), response=True)
    except Exception:  # noqa: BLE001
        return False
    return True


async def find_ceiling(
    client: BleakClient, name: str, uuid: str, known_good: int, known_bad: int = 100
) -> int:
    """Binary-search the highest value accepted via a with-response write.

    Assumes accept/reject is monotonic (everything <= the ceiling is fine,
    everything above it is rejected) -- true for a simple range check, but
    would give a misleading answer if the real constraint is instead some
    scattered set of allowed values.
    """
    if not await accepts(client, uuid, known_good):
        print(f"{name}: anchor value {known_good} was rejected -- can't binary search, skipping")
        return known_good
    if await accepts(client, uuid, known_bad):
        print(f"{name}: {known_bad} was accepted -- no ceiling found below it")
        return known_bad

    lo, hi = known_good, known_bad
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if await accepts(client, uuid, mid):
            lo = mid
        else:
            hi = mid
    print(f"{name}: highest accepted value (with-response) = {lo}")
    return lo


async def main(address: str) -> None:
    async with BleakClient(address) as client:
        await dump_properties(client)
        await dump_values(client, "before")

        originals: dict[str, int] = {}
        print("\n--- binary-searching write ceilings ---")
        for name, (uuid, known_good) in RANGE_TARGETS.items():
            originals[uuid] = await safe_read_byte(client, uuid, known_good)
            await find_ceiling(client, name, uuid, known_good)

        print("\n--- restoring original values ---")
        for uuid, original in originals.items():
            try:
                await client.write_gatt_char(uuid, bytes([original]), response=True)
                print(f"restored {uuid} = {original}")
            except Exception as exc:  # noqa: BLE001
                print(f"could not restore {uuid} to {original}: {exc!r}")

        await dump_values(client, "after")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
