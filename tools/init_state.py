#!/usr/bin/env python3
"""Reset a Nightingale unit to a known-good baseline state.

Built after track_probe.py corrupted Relax sound track's live value by
writing 1-byte test values into what turned out to be a 2-byte
characteristic -- the true original, recovered from an earlier run's
logged "current raw value" line, was b'\\x01\\xfe' (soundIndex 510 =
"Lakeshore"). Sleep sound track's original value, b'\\x05\\x00'
(1280), turned out to have never been a valid blanket id at all --
decompiled Blanket.java's index arithmetic (roomStyle 100/200/300 +
roomType offset 10/15/20/25/30) only produces values 110-330, so this
now writes a real one (Adult Bedroom Blanket, Absorptive = 110)
instead of restoring a value that was always non-functional. See
PROTOCOL.md.

Sets:
- Sound status: on
- Light status: on
- Sound mode: Nature Sound (required for Relax volume/track to be the
  *live* profile -- see PROTOCOL.md; without this, the values below
  get written successfully but silently do nothing audible. Sleep
  sound track is still set below regardless, so it's parked correctly
  for whenever you switch modes, even though it won't be audible until
  Sound Mode is Sound Blanket)
- Sleep volume, Relax volume, Light level: 5 (middle of the confirmed
  0-10 range)
- Sleep sound track: a confirmed-valid blanket id (Adult Bedroom
  Blanket, Absorptive)
- Relax sound track: the recovered original raw value (Lakeshore)

Also useful going forward as a clean, fully-known starting point before
any exploratory testing, rather than accumulating drift across many
separate manual test sessions -- which is what led to the track-index
confusion this script exists to fix in the first place.

Run this directly against a unit -- NOT through Home Assistant or an
ESPHome proxy. Disable or reload-off the Nightingale config entry in HA
first, or this will just fail to connect.

Usage:
    pip install bleak
    python3 init_state.py AA:BB:CC:DD:EE:FF
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient

SOUND_STATUS_UUID = "cc339aad-1847-42ed-a606-3e0a9b3bfca5"
LIGHT_STATUS_UUID = "6e31cc36-4901-432f-aed1-cc5f87009853"
SOUND_MODE_UUID = "1eb5c56d-5970-4294-9208-f16d66c396ef"
SLEEP_VOLUME_UUID = "6dd68afc-9d26-4e67-95cb-c56c784360e7"
RELAX_VOLUME_UUID = "bb23ae19-b2f0-46f4-930d-d89047d92c06"
LIGHT_LEVEL_UUID = "adfa5e07-ebe3-4362-ae05-b63cc5aad5b1"
SLEEP_SOUND_TRACK_UUID = "a54d9906-4298-4656-9bd3-7095e87365d6"
RELAX_SOUND_TRACK_UUID = "0e4fa979-6e76-45f0-8887-762ee399121c"

NATURE_SOUND = 0x01
MIDDLE_VOLUME = 5
# Adult Bedroom Blanket, Absorptive -- confirmed valid via decompiled
# Blanket.java (roomStyle 100 + roomType offset 10), unlike the
# previous recovered-but-dead b'\x05\x00'.
DEFAULT_SLEEP_TRACK = (110).to_bytes(2, "big")
# Lakeshore -- confirmed valid via decompiled Room.java, and the real
# original value recovered from a pre-incident log line.
RECOVERED_RELAX_TRACK = bytes.fromhex("01fe")

# (label, characteristic uuid, bytes to write)
STEPS: list[tuple[str, str, bytes]] = [
    ("Sound status", SOUND_STATUS_UUID, b"\x01"),
    ("Light status", LIGHT_STATUS_UUID, b"\x01"),
    ("Sound mode", SOUND_MODE_UUID, bytes([NATURE_SOUND])),
    ("Sleep volume", SLEEP_VOLUME_UUID, bytes([MIDDLE_VOLUME])),
    ("Relax volume", RELAX_VOLUME_UUID, bytes([MIDDLE_VOLUME])),
    ("Light level", LIGHT_LEVEL_UUID, bytes([MIDDLE_VOLUME])),
    ("Sleep sound track", SLEEP_SOUND_TRACK_UUID, DEFAULT_SLEEP_TRACK),
    ("Relax sound track", RELAX_SOUND_TRACK_UUID, RECOVERED_RELAX_TRACK),
]


async def main(address: str) -> None:
    async with BleakClient(address) as client:
        print("--- writing baseline state ---")
        for label, uuid, value in STEPS:
            try:
                await client.write_gatt_char(uuid, value, response=True)
                print(f"OK   {label} <- {value!r}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {label} <- {value!r}: {exc!r}")

        print("\n--- resulting values ---")
        for label, uuid, _value in STEPS:
            try:
                data = await client.read_gatt_char(uuid)
                print(f"{label:20s} = {data!r}")
            except Exception as exc:  # noqa: BLE001
                print(f"{label:20s} read failed: {exc!r}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} AA:BB:CC:DD:EE:FF")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
