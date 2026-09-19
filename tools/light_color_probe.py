#!/usr/bin/env python3
"""Test whether the light accepts arbitrary RGB, not just the app's 4.

The vendor app never sends anything but White/Red/Green/Blue -- traced
to a hardcoded switch keyed by which button you tapped (index 1-4),
not an actual RGB byte extraction (see PROTOCOL.md, "Confirmed: Light
Color Is Exactly 4 Colors"). That's a pure software choice with no
evidence either way about what the firmware itself would accept for a
3-byte RGB characteristic on what's almost certainly a plain 3-channel
LED. This writes a handful of clearly-non-preset colors, reads the
value back immediately after each (to see if the device silently
clamps/snaps it to something else), and asks what the light actually
looks like -- both signals together are stronger evidence than either
alone.

Forces Light on and to a reasonably bright level for the test (both
restored afterward, along with the original color), since a dim or off
light makes any color difference hard to see.

Run this directly against a unit -- NOT through Home Assistant or an
ESPHome proxy. Disable or reload-off the Nightingale config entry in HA
first, or this will just fail to connect.

Usage:
    pip install bleak
    python3 light_color_probe.py AA:BB:CC:DD:EE:FF
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient

LIGHT_STATUS_UUID = "6e31cc36-4901-432f-aed1-cc5f87009853"
LIGHT_LEVEL_UUID = "adfa5e07-ebe3-4362-ae05-b63cc5aad5b1"
LIGHT_COLOR_UUID = "4bf0b1b1-aadc-47aa-b5fb-c7f9affa2462"

TEST_LEVEL = 8  # confirmed 0-10 range; bright enough to see color clearly

# A mix of non-preset colors: clear blends, a pastel, and a dim shade of
# a preset color, to see whether the device snaps toward White/R/G/B or
# actually renders something in between.
TEST_COLORS: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("Purple", (0x80, 0x00, 0xC0)),
    ("Orange", (0xFF, 0x80, 0x00)),
    ("Cyan", (0x00, 0xC0, 0xC0)),
    ("Warm white", (0xFF, 0xC0, 0x80)),
    ("Dim red", (0x40, 0x00, 0x00)),
)


async def main(address: str) -> None:
    async with BleakClient(address) as client:
        original_status = bytes(await client.read_gatt_char(LIGHT_STATUS_UUID))
        original_level = bytes(await client.read_gatt_char(LIGHT_LEVEL_UUID))
        original_color = bytes(await client.read_gatt_char(LIGHT_COLOR_UUID))
        print(
            f"original status={original_status!r} level={original_level!r} "
            f"color={original_color!r}"
        )

        await client.write_gatt_char(LIGHT_STATUS_UUID, b"\x01", response=True)
        await client.write_gatt_char(
            LIGHT_LEVEL_UUID, bytes([TEST_LEVEL]), response=True
        )
        print(f"Light forced on at level {TEST_LEVEL} for this test")

        for name, rgb in TEST_COLORS:
            candidate = bytes(rgb)
            try:
                await client.write_gatt_char(LIGHT_COLOR_UUID, candidate, response=True)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name} {candidate.hex()}: write rejected: {exc!r}")
                continue
            readback = bytes(await client.read_gatt_char(LIGHT_COLOR_UUID))
            match = (
                "matches what was written"
                if readback == candidate
                else f"device reports {readback.hex()} instead"
            )
            description = input(
                f"Wrote {name} ({candidate.hex()}). Readback: {readback.hex()} "
                f"({match}). What does the light actually look like? "
            )
            print(f"  -> you said: {description!r}")

        print("\n--- restoring original state ---")
        for uuid, original in (
            (LIGHT_COLOR_UUID, original_color),
            (LIGHT_LEVEL_UUID, original_level),
            (LIGHT_STATUS_UUID, original_status),
        ):
            try:
                await client.write_gatt_char(uuid, original, response=True)
                print(f"restored {uuid} = {original!r}")
            except Exception as exc:  # noqa: BLE001
                print(f"could not restore {uuid} to {original!r}: {exc!r}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
