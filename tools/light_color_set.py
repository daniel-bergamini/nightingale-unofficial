#!/usr/bin/env python3
"""Set the light to an arbitrary RGB value and leave it there to look at.

Generic, one-shot version of light_color_probe.py's fixed test matrix --
takes any RGB value as a command-line argument instead of walking
through a hardcoded list. Unlike light_color_probe.py, this does NOT
restore the original color afterward: the whole point is to leave the
light showing the result so you can actually look at it. It does print
the original value before changing anything, so you can restore it
later by just re-running this tool with that value.

Forces Light on at the given (or default) level, since a dim or off
light makes any color hard to see -- also left as-is afterward, not
restored.

Run this directly against a unit -- NOT through Home Assistant or an
ESPHome proxy. Disable or reload-off the Nightingale config entry in HA
first, or this will just fail to connect.

Usage:
    pip install bleak
    python3 light_color_set.py AA:BB:CC:DD:EE:FF RRGGBB [level]

Examples:
    python3 light_color_set.py B3:E3:EE:18:00:C0 800000        # dim red alone
    python3 light_color_set.py B3:E3:EE:18:00:C0 008000        # dim green alone
    python3 light_color_set.py B3:E3:EE:18:00:C0 000080        # dim blue alone
    python3 light_color_set.py B3:E3:EE:18:00:C0 FF8000 10     # orange, full brightness
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient

LIGHT_STATUS_UUID = "6e31cc36-4901-432f-aed1-cc5f87009853"
LIGHT_LEVEL_UUID = "adfa5e07-ebe3-4362-ae05-b63cc5aad5b1"
LIGHT_COLOR_UUID = "4bf0b1b1-aadc-47aa-b5fb-c7f9affa2462"

DEFAULT_LEVEL = 8  # confirmed 0-10 range


def parse_rgb(hex_str: str) -> bytes:
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) != 6:
        raise ValueError(f"expected 6 hex digits (RRGGBB), got {hex_str!r}")
    return bytes.fromhex(hex_str)


async def main(address: str, rgb: bytes, level: int) -> None:
    async with BleakClient(address) as client:
        original_status = bytes(await client.read_gatt_char(LIGHT_STATUS_UUID))
        original_level = bytes(await client.read_gatt_char(LIGHT_LEVEL_UUID))
        original_color = bytes(await client.read_gatt_char(LIGHT_COLOR_UUID))
        print(
            f"original status={original_status!r} level={original_level!r} "
            f"color={original_color.hex()} -- rerun with this color value to "
            "restore it manually"
        )

        await client.write_gatt_char(LIGHT_STATUS_UUID, b"\x01", response=True)
        await client.write_gatt_char(LIGHT_LEVEL_UUID, bytes([level]), response=True)
        await client.write_gatt_char(LIGHT_COLOR_UUID, rgb, response=True)

        readback = bytes(await client.read_gatt_char(LIGHT_COLOR_UUID))
        match = "matches" if readback == rgb else f"MISMATCH, device reports {readback.hex()}"
        print(f"set color to {rgb.hex()} at level {level} -- readback {readback.hex()} ({match})")
        print("left as-is; nothing was restored")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF RRGGBB [level]")
        sys.exit(1)
    address_arg = sys.argv[1]
    rgb_arg = parse_rgb(sys.argv[2])
    level_arg = int(sys.argv[3]) if len(sys.argv) == 4 else DEFAULT_LEVEL
    asyncio.run(main(address_arg, rgb_arg, level_arg))
