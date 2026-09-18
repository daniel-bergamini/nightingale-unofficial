# Nightingale BLE Protocol (Unofficial)

Reverse-engineered from the official Android app (`bluerocket.cambridgesoundmanagement`,
package name unchanged since ~2017) by decompiling with `jadx`. Documented here in the
author's own words — no vendor source is reproduced in this repo.

Applies to: Cambridge Sound Management / Nightingale Smart Solutions **NG2000**
("Nightingale Smart Home Sleep System"). FCC ID `2AJX6-NG2000`. Radio module: USI
WM-N-BM-30 (Cypress/Infineon WICED-based Wi-Fi + BLE combo).

## Background

Nightingale was cloud-connected via Ayla Networks for WiFi-based features (scheduling,
IFTTT, Alexa/Google integration). That backend, and the iOS app, are no longer available
as of 2024–2025. The device's Bluetooth Low Energy interface is fully local and requires
no cloud account, no pairing PIN, and no vendor app — this is the interface documented
below.

## Primary Service

All functional characteristics live under one service:

```
ngServiceUUID = 80b03553-ac03-41bc-8d3c-931f0a330168
```

Confirmed live via `bluetoothctl info` against a physical unit (2026-09-18): advertises this service UUID and local name `Nightingale` (`Name:`/`Alias:` both read exactly `Nightingale`, no suffix or per-unit distinguishing string).

## Characteristics

### Power / Status

| Name | UUID | Format |
|---|---|---|
| Sound status (immediate on/off) | `cc339aad-1847-42ed-a606-3e0a9b3bfca5` | 1 byte, `0x00`/`0x01` |
| Light status (immediate on/off) | `6e31cc36-4901-432f-aed1-cc5f87009853` | 1 byte, `0x00`/`0x01` |
| Sound mute | `74ba593d-506d-435e-becf-dc84069f24f8` | 1 byte, `0x00`/`0x01` |

### Sound

| Name | UUID | Format |
|---|---|---|
| Sound mode | `1eb5c56d-5970-4294-9208-f16d66c396ef` | 1 byte, enum ordinal — `0x00` = Sound Blanket, `0x01` = Nature Sound |
| Sleep volume | `6dd68afc-9d26-4e67-95cb-c56c784360e7` | 1 byte, `0x00`–`0x0A` (0–10, an 11-step level — **not** 0–100%; see "Confirmed: Real Range Is 0–10" below). Write succeeds; **live A/B tested and found to have no audible effect** on playback — real function unknown. |
| Relax volume | `bb23ae19-b2f0-46f4-930d-d89047d92c06` | 1 byte, `0x00`–`0x0A` assumed (0–10, carried over from sleep volume/light level's independently-binary-searched ceiling, not separately re-verified). **Live A/B tested and confirmed to audibly control live playback** — despite the name, this is the volume control that actually does something right now. |
| Page volume | ~~`f2e85c5e6-97a4-4c3a-9742-5278bf3881ec`~~ — **invalid, unusable** | 1 byte, `0x00`–`0x64` (unverified) |
| Volume balance (L/R) | `c32f5045-d621-4c9e-8f9b-557b5a5d65cd` | Integer, likely signed for L/R skew (unverified) |
| Sleep sound track | `a54d9906-4298-4656-9bd3-7095e87365d6` | **Confirmed 2 bytes** (original value `b'\x05\x00'`), but the `BedroomBlanket` id scheme isn't traced yet — see "Confirmed: Nature Sound Track Is a Big-Endian soundIndex" below (unverified — do not guess valid values) |
| Relax sound track | `0e4fa979-6e76-45f0-8887-762ee399121c` | **Confirmed**: big-endian 16-bit `soundIndex` — see `NATURE_SOUND_TRACKS` in `protocol.py` and "Confirmed: Nature Sound Track Is a Big-Endian soundIndex" below |
| Sound scheduled (enable flag) | `86dcd724-031d-4ebe-a2e1-912670a06c3c` | Integer, likely `0x00`/`0x01` (unverified) |
| **Sound auto-on time** ⚠️ not an immediate toggle | `11104650-14be-436b-a900-b72763c3be82` | 2 bytes: `[minute, hour]`, both plain integers, 24hr |
| **Sound auto-off time** ⚠️ not an immediate toggle | `5e6379e1-bd5b-44a2-ac16-74f845d6c388` | 2 bytes: `[minute, hour]`, same format |

### Light

| Name | UUID | Format |
|---|---|---|
| Light level | `adfa5e07-ebe3-4362-ae05-b63cc5aad5b1` | 1 byte, `0x00`–`0x0A` (0–10, same 11-step level as sleep volume; see below) |
| Light color | `4bf0b1b1-aadc-47aa-b5fb-c7f9affa2462` | 3 bytes, RGB. Confirmed: White `FF FF FF`, Green `00 FF 00`, Blue `00 00 FF`. Inferred: Red `FF 00 00` |
| Light scheduled (enable flag) | `8ae4953e-0db8-11e6-a148-3e1d05defe78` | Integer, likely `0x00`/`0x01` (unverified) |
| **Light auto-on time** | `0eef9fab-7878-4e33-9201-f9029a342530` | 2 bytes: `[minute, hour]`, same schedule format as sound |
| **Light auto-off time** | `36d5794c-091d-4e3e-8146-af0477e240a7` | 2 bytes: `[minute, hour]`, same |

### Device / Misc

| Name | UUID | Format |
|---|---|---|
| Disable physical button | `b686b17d-b0dd-4415-bb76-895745d9d5ed` | Integer (unverified) |
| Room name | `add88f42-6127-41e7-8f0e-de054d99d91d` | String |
| Location name | `37c4cabf-3f32-40ef-8ee3-92db35671faa` | String |
| Ramp (fade-in duration) | `7c54068a-46a7-42c9-a318-f5d47f492028` | Integer (unverified) |
| Flash-when-updated indicator | `370ffb49-7626-4531-8b22-dbdeb359a304` | Integer (unverified) |
| On/Off (legacy?) | `c7d62e9d-c352-43b5-a00a-939254cfb3ca` | Unknown — not wired to any method in the decompiled app; likely vestigial from an earlier firmware revision. **Do not assume this is the power toggle** — use the Status characteristics above instead. |

### WiFi / Cloud Provisioning (dead weight — documented for completeness only)

Service `9593fe2e-e54c-4dce-9227-c995ed026591` and a cluster of SSID/security/DSN/reg-token
characteristics exist for onboarding the device onto the Ayla Networks cloud over BLE.
Since that backend is discontinued, **this entire branch of the protocol is
non-functional** and shouldn't be pursued — the device requires a DSN + registration
token handshake with Ayla's cloud to complete WiFi setup, which will not succeed for an
orphaned product line.

## Confirmed: Real Range Is 0–10, Not 0–100

Sleep volume and light level were originally documented as `0x00`–`0x64`
(0–100%) purely by inference from the decompiled app's naming and the
single-byte shape it shared with confirmed characteristics like the
Status flags — the same "confirmed" bar every other entry here uses when
it's traced to construction code but not yet live-tested. Live testing
(2026-09-18) against a physical unit proved that inference wrong:

- Both characteristics' actual GATT properties are `['notify', 'read',
  'write']` — full support for with-response writes, ruling out a
  write-mode mismatch.
- A with-response write above a device-enforced ceiling gets rejected
  with a GATT Application Error (ATT error code `0x80`) — a real
  firmware-side range check, not a permissions or state issue.
- Binary-searching that ceiling (`tools/gatt_probe.py`) converged
  cleanly on **10** for both characteristics independently: `10` is
  accepted, `11` is rejected.
- `write-without-response` is not a reliable way to probe this: it
  reports success locally the instant the packet is queued, with no
  ATT-level confirmation, so the firmware silently dropping an
  out-of-range value under that write mode looks identical to it being
  accepted. Only `with-response` results are trustworthy here.

So both are 11-step (`0`–`10`) level controls, not percentages.

## Confirmed: Relax Volume, Not Sleep Volume, Controls Live Playback

With sleep volume's range fixed, a follow-up puzzle came up: raising it
produced no audible change at all, on a unit actively playing a nature
sound loop with sound/light both on. Rather than assume the
characteristic was simply broken, an A/B listening test
(`tools/volume_ab_probe.py`, 2026-09-18) wrote a quiet value then a loud
value to each of sleep volume and relax volume in turn, pausing for a
human to actually listen:

- Sleep volume: write succeeds, **no audible change** either direction.
- Relax volume: write succeeds, **clearly audible change** both
  directions.

So despite the name, **relax volume is the characteristic that actually
gain-controls whatever's currently playing** — the same kind of
vendor-naming trap as `SoundOn`/`SoundOff` turning out to be schedule
setters rather than the power toggle (see "Notes on Schedule vs.
Immediate Control" below).

## Confirmed: Sound Mode Selects Which Volume Profile Is Live

Follow-up testing in Home Assistant (toggling the Sound Mode select)
found sleep volume isn't dead: it's live exactly when sound mode is
`SOUND_BLANKET` (`0x00`), and relax volume is live exactly when sound
mode is `NATURE_SOUND` (`0x01`). So this device really does have two
distinct sound profiles, each with its own volume, and `SOUND_MODE_UUID`
is what selects between them — not just a content-genre picker as its
decompiled naming alone suggested. This also matches the still-unverified
separate sleep/relax sound-track characteristics: a consistent two-profile
design throughout, not a coincidence.

Practical effect for the integration: adjusting Sleep Volume only has an
audible effect while Sound Mode is set to Sound Blanket, and Relax
Volume only while it's set to Nature Sound. Both stay as separate
entities under their full vendor names.

## Caution: Relax Sound Track Is (At Least) 2 Bytes, Not 1

While probing the still-unverified sleep/relax sound-track
characteristics (`tools/track_probe.py`), cycling `RELAX_SOUND_TRACK_UUID`
through single-byte index values (`0x00`-`0x09`) and then writing back
the exact bytes read before the test started did **not** reliably
restore the original audio. A power cycle fixed it once, but not on a
second occurrence.

The root cause only became clear from an earlier run's logged output:

```
current raw value: b'\x01\xfe'
```

That's **2 bytes**, not 1. Every probe write up to this point —
`bytes([index])` for `index` in `0..9` — wrote a single byte into a
characteristic that actually holds two, matching neither this
protocol's usual single-byte convention nor the schedule
characteristics' `[minute, hour]` pair convention exactly (format
otherwise still unconfirmed — could be two independent bytes, or one
16-bit value in either endianness). `RELAX_SOUND_TRACK_UUID`'s "Integer
index" description in this table never specified a width; that
assumption (1 byte, matching every other numeric characteristic here)
turned out to be wrong for this one.

**Recovered.** Writing the recovered raw value (`01 FE`) back via
`tools/init_state.py` (which also sets Sound/Light on, Sound Mode to
Nature Sound, and all volumes to 5) restored the original audio —
crickets plus what's more likely a tree frog than a bird, on reflection.

A follow-up read-only check (`tools/track_probe.py`, no `--write`)
confirmed `SLEEP_SOUND_TRACK_UUID` is also 2 bytes, original value
`b'\x05\x00'`. So both sound-track characteristics are 2 bytes on this
unit; `tools/init_state.py` now restores both. Relax sound track's
exact encoding is now decoded (see next section); Sleep sound track's
is not.

Practical implication for anyone probing this further: don't assume
byte width from naming or from sibling characteristics. Read and log
the actual current value **before** writing anything, for every
characteristic, every time — the exact lesson `tools/init_state.py`
and this incident exist to reinforce.

## Confirmed: Nature Sound Track Is a Big-Endian soundIndex

Decompiled source settled what the 2 bytes actually mean, at least for
Relax sound track. `bluerocket/cgm/model/Room.java`'s constructor builds
its Nature Sound list like this (names condensed from the real
if/equals chain):

```java
if (natureSound.name.get().equals("Lakeshore"))   natureSound.soundIndex.set(510);
if (natureSound.name.get().equals("Crickets"))    natureSound.soundIndex.set(520);
if (natureSound.name.get().equals("Loons"))       natureSound.soundIndex.set(530);
if (natureSound.name.get().equals("Whale Songs")) natureSound.soundIndex.set(540);
if (natureSound.name.get().equals("Rainstorm"))   natureSound.soundIndex.set(550);
```

The recovered original value, `b'\x01\xfe'`, read as a **big-endian
16-bit integer** is `0x01FE = 510` — exactly `soundIndex` for
"Lakeshore". Not a coincidence: that's the wire format. (This also
retroactively explains the "crickets and a tree frog" description
better than a literal name match would have — a lakeshore-at-night
ambiance plausibly includes both as part of the scene.)

`RELAX_SOUND_TRACK_UUID` is now a first-class confirmed characteristic:
`encode_nature_sound_track`/`decode_nature_sound_track` in `protocol.py`
handle the big-endian conversion, and `NATURE_SOUND_TRACKS` holds the
name→`soundIndex` map above. Wired up as the "Relax Sound Track" select
entity.

Sleep sound track's original value, `b'\x05\x00'` (`0x0500 = 1280`
big-endian), doesn't match this numbering and remains unverified —
`NatureSound extends BedroomBlanket` in the decompiled model, so the
generic `BedroomBlanket` class likely has its own id scheme entirely
separate from `NatureSound.soundIndex`. Not yet traced.

## Known Vendor Bug: Page Volume UUID

`ngVolumePageUUID` in `NightingaleGatt.java` (line 55) is declared as:

```java
public static final UUID ngVolumePageUUID = UUID.fromString("f2e85c5e6-97a4-4c3a-9742-5278bf3881ec");
```

That string has 9 hex digits in its first group instead of 8 — not a valid
UUID. `UUID.fromString()` throws `IllegalArgumentException` on it, so any
code path that touches this field is dead: it would have crashed the
vendor's own app immediately if it were ever actually invoked. This isn't
a transcription error in this repo — it's a genuine bug in the shipped
app, confirmed against the decompiled source. Treat "Page volume" as
unimplementable until/unless the correct UUID can be recovered some other
way (e.g. a GATT services dump directly off a physical unit).

## Confirmed vs. Unverified

Entries marked "confirmed" above were traced to an actual byte-construction call site in
the decompiled app (`BigInteger.toByteArray()`, a manual `byte[]`, or a `ByteBuffer` build)
and/or tested live against a physical unit. Entries marked "(unverified)" are inferred
purely from naming and sibling-characteristic pattern-matching — same service, same
apparent single-byte-percentage shape as confirmed neighbors — but haven't been traced to
their construction code or tested live yet. Treat unverified entries as a starting guess,
not a guarantee.

## Notes on Schedule vs. Immediate Control

A recurring gotcha during reverse-engineering: characteristics named "SoundOn"/"SoundOff"
and "LightOn"/"LightOff" are **not** immediate power toggles — they're the app's
auto-schedule feature (turn on before bedtime, off before waking), taking a
`[minute, hour]` time pair. The actual immediate power toggles are the separate "Status"
characteristics (`ngStatusUUID`, `ngLightStatusUUID`). This naming is the vendor's own
inconsistency, not a translation error in this repo.

## Tooling Used

- `jadx` for APK decompilation
- Live testing via `bluetoothctl` (BlueZ) and `nRF Connect`
- Confirmed working control path: `bleak` (Python) direct writes; Home Assistant custom
  integration via `bleak-retry-connector` + Bluetooth Proxy (ESPHome
  `bluetooth_proxy: active`)
