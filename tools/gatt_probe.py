#!/usr/bin/env python3
"""Diagnose GATT write failures against a physical Nightingale unit directly.

Written to chase down "Application Error 0x80" on Sleep Volume / Light Level
writes: dumps each characteristic's actual declared GATT properties (this
alone usually reveals a write-mode mismatch), reads current values, then
sweeps a few values and write modes (with-response vs without-response) to
see exactly what the firmware accepts vs rejects.

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


async def try_write(
    client: BleakClient, name: str, uuid: str, value: int, response: bool
) -> None:
    mode = "with-response" if response else "without-response"
    try:
        await client.write_gatt_char(uuid, bytes([value]), response=response)
        print(f"OK   {name} <- {value} ({mode})")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {name} <- {value} ({mode}): {exc!r}")


async def sweep(client: BleakClient, name: str, uuid: str, current: int) -> None:
    nudge = current + 1 if current < 100 else current - 1
    print(f"\n--- write attempts: {name} (current={current}) ---")
    for value in (nudge, 0, 50, 100):
        for response in (True, False):
            await try_write(client, name, uuid, value, response)


async def main(address: str) -> None:
    async with BleakClient(address) as client:
        await dump_properties(client)
        await dump_values(client, "before")

        current_volume = await safe_read_byte(client, SLEEP_VOLUME_UUID, 50)
        await sweep(client, "Sleep volume", SLEEP_VOLUME_UUID, current_volume)

        current_level = await safe_read_byte(client, LIGHT_LEVEL_UUID, 50)
        await sweep(client, "Light level", LIGHT_LEVEL_UUID, current_level)

        await dump_values(client, "after")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
