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
| Sleep volume | `6dd68afc-9d26-4e67-95cb-c56c784360e7` | 1 byte, `0x00`–`0x0A` (0–10, an 11-step level — **not** 0–100%; see "Confirmed: Real Range Is 0–10" below). Only audible while Sound Mode is Sound Blanket — see "Confirmed: Sound Mode Selects Which Volume Profile Is Live" below. |
| Relax volume | `bb23ae19-b2f0-46f4-930d-d89047d92c06` | 1 byte, `0x00`–`0x0A` assumed (0–10, carried over from sleep volume/light level's independently-binary-searched ceiling, not separately re-verified). Only audible while Sound Mode is Nature Sound. |
| Page sound (test tone trigger) | `6500a2cd-6b0d-494a-af32-878b5bfa45cd` | Big-endian 16-bit `soundIndex`, same shape as the Sleep/Relax track characteristics (unverified format/value). One-shot device-setup test-tone trigger, not an ongoing mode — see "Known Vendor Bug: Page Volume UUID (Recovered, Not a Dead End)" below |
| Page volume (test tone) | ~~`f2e85c5e6-97a4-4c3a-9742-5278bf3881ec`~~ (typo in `NightingaleGatt.java`) → real UUID `2e85c5e6-97a4-4c3a-9742-5278bf3881ec` (from `BleManager.java`) | Format unverified. Recovered, not unusable — see "Known Vendor Bug" below |
| Volume balance (L/R) | `c32f5045-d621-4c9e-8f9b-557b5a5d65cd` | **Confirmed**: signed 1 byte, `-10`–`10` — `setBalance(Integer)`: `if (balance >= -10 && balance <= 10) { byte[] output = {(byte) balance.intValue()}; ...}` (`LeNightingaleDevice.java`) |
| Sleep sound track | `a54d9906-4298-4656-9bd3-7095e87365d6` | **Confirmed**: big-endian 16-bit `soundIndex`, same format as Relax sound track — vendor's own app picks this from two independent dimensions, Room Type × Surface Type, not one flat value; see "Confirmed: Bedroom Blanket Ids" → "Room Type / Surface Type, Not One Flat List" below |
| Relax sound track | `0e4fa979-6e76-45f0-8887-762ee399121c` | **Confirmed**: big-endian 16-bit `soundIndex` — see `NATURE_SOUND_TRACKS` in `protocol.py` and "Confirmed: Nature Sound Track Is a Big-Endian soundIndex" below |
| Sound scheduled (enable flag) | `86dcd724-031d-4ebe-a2e1-912670a06c3c` | **Confirmed**: 1 byte, `0x00`/`0x01` — `setSoundScheduled(1)`/`setSoundScheduled(0)` called with literal integers (`SetSleepScheduleFragment.java`) |
| **Sound auto-on time** ⚠️ not an immediate toggle | `11104650-14be-436b-a900-b72763c3be82` | 2 bytes: `[minute, hour]`, both plain integers, 24hr |
| **Sound auto-off time** ⚠️ not an immediate toggle | `5e6379e1-bd5b-44a2-ac16-74f845d6c388` | 2 bytes: `[minute, hour]`, same format |

### Light

| Name | UUID | Format |
|---|---|---|
| Light level | `adfa5e07-ebe3-4362-ae05-b63cc5aad5b1` | 1 byte, `0x00`–`0x0A` (0–10, same 11-step level as sleep volume; see below) |
| Light color | `4bf0b1b1-aadc-47aa-b5fb-c7f9affa2462` | 3 bytes, RGB. Confirmed: White `FF FF FF`, Green `00 FF 00`, Blue `00 00 FF`. Inferred: Red `FF 00 00` |
| Light scheduled (enable flag) | `8ae4953e-0db8-11e6-a148-3e1d05defe78` | **Confirmed**: 1 byte, `0x00`/`0x01`, same as Sound scheduled |
| **Light auto-on time** | `0eef9fab-7878-4e33-9201-f9029a342530` | 2 bytes: `[minute, hour]`, same schedule format as sound |
| **Light auto-off time** | `36d5794c-091d-4e3e-8146-af0477e240a7` | 2 bytes: `[minute, hour]`, same |

### Device / Misc

| Name | UUID | Format |
|---|---|---|
| Disable physical button | `b686b17d-b0dd-4415-bb76-895745d9d5ed` | **Confirmed**: 1 byte, `0x00`/`0x01` — `setDisableBtn(Integer)` switches on the literal values `0`/`1` (`LeNightingaleDevice.java`) |
| Ramp (fade-in duration) | `7c54068a-46a7-42c9-a318-f5d47f492028` | **Confirmed 1 byte**, but the app's own bounds check doesn't match: `setRamp(Integer ramp)` validates `ramp <= 360` then does `(byte) ramp.intValue()` — a Java byte cast silently wraps for anything above 127. Real safe range unconfirmed; not wired to an entity |
| Flash-when-updated indicator | `370ffb49-7626-4531-8b22-dbdeb359a304` | No references anywhere in the decompiled app outside its own declaration — likely vestigial (unverified) |
| Room name | `add88f42-6127-41e7-8f0e-de054d99d91d` | String |
| Location name | `37c4cabf-3f32-40ef-8ee3-92db35671faa` | String |
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

Independent corroboration turned up later, in a 2016 New Atlas review's
product photo of the actual app UI (iOS/Android/web, per its caption):
the volume dial reads a plain integer ("4", "5" in different screenshots)
— matching the 0–10 scale found by binary search, not a coincidence —
and there's a visible toggle switch labeled **"Sleep Blanket Mode"** /
**"Soothing Sounds Mode"**, the exact same enum as `SOUND_MODE_UUID`
under slightly different marketing wording than "Sound Blanket"/"Nature
Sound". The photographed room, labeled "Infant, Toddler & Kids Room
Blanket", is a *third* variant of the Kids room type's name (see "Room
Type / Surface Type, Not One Flat List" below for the other two) — this
vendor was never consistent about that one room type's name across any
of its own surfaces.

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
`encode_sound_track_id`/`decode_sound_track_id` in `protocol.py` handle
the big-endian conversion, and `NATURE_SOUND_TRACKS` holds the
name→`soundIndex` map above. Wired up as the "Relax Sound Track" select
entity, and live-confirmed further: cycling through all 5 options in HA
matched what was actually heard for each one.

Sleep sound track's original value, `b'\x05\x00'` (`0x0500 = 1280`
big-endian), doesn't match this numbering — `NatureSound extends
BedroomBlanket` in the decompiled model, so the generic `BedroomBlanket`
class has its own id scheme entirely separate from `NatureSound.soundIndex`,
traced in the next section.

## Confirmed: Bedroom Blanket Ids

Switching Sound Mode to Sound Blanket and turning Sleep Volume all the
way up produced no audio at all — the immediate suspicion was a missing
"enable" step, but decompiled `RoomFragment.java` ruled that out
directly: the app's `nightingaleBlanketEnabled` flag is purely a UI
concept that maps straight onto `SOUND_MODE_UUID`
(`device.setSoundMode(nightingaleBlanketEnabled ? BLANKET :
NATURE_SOUND)`), the same characteristic already wired up. Nothing
missing there.

The real answer was in `Blanket.java`'s index arithmetic:

```java
// roomStyleIndex: Absorptive=100, Neutral=200, Reflective=300
// roomTypeIndex offset: Bedroom=+10, Kids=+15, Snoring=+20, Tinnitus=+25, Hospital=+30
blanketIndex = roomStyleIndex + <offset for roomTypeIndex>;
```

3 styles × 5 types = **15 values** (matching the "15 sound blankets"
marketing claim exactly): `110, 115, 120, 125, 130, 210, 215, 220, 225,
230, 310, 315, 320, 325, 330`. `Blanket.getAllBlankets()` confirms this
set directly with three explicit loops (`110..130`, `210..230`,
`310..330`, all step `5`), so all 15 — including Hospital's `+30`,
initially inferred from pattern before a local decompiled source copy
let this get checked directly — are now source-confirmed, not guessed.

`1280` (Sleep sound track's restored-but-dead original value) isn't in
this list — so the write path was never broken, there was simply
nothing valid selected. `BEDROOM_BLANKETS` in `protocol.py` holds the
full name→id map for reference (matches PROTOCOL.md/README), derived
from the two dimensions below rather than hand-maintained separately.
`tools/init_state.py` writes a real value (`110`, Adult Bedroom
Blanket/Absorptive) instead of restoring the non-functional `1280`.

### Room Type / Surface Type, Not One Flat List

A flat 15-item picker is a poor match for how the vendor's own app
actually presents this. `SelectingBlanketFragment.java` — part of the
setup wizard — picks a Blanket from two independent controls, per its
own argument constants:

```java
public static final String ARG_ROOM_TYPE = "roomType";
public static final String ARG_SURFACE_TYPE = "surfaceType";
```

So the two vendor-defined dimensions are literally **Room Type**
(Adult Bedroom, Youth Bedroom, Snoring Condition, Tinnitus Condition,
Hospital Room) and **Surface Type** (Absorptive, Neutral, Reflective).
All of these are now confirmed exact — extracted directly from the
APK's compiled resource table with `androguard`, not inferred from
resource-id naming as originally documented (this repo initially had
no way to read compiled resource values, only decompiled Java source;
see "Extracting Compiled Resources, Not Just Decompiled Source" below).
That extraction also caught three labels this repo had wrong: the
picker actually says "Youth Bedroom", "Snoring Condition", and
"Tinnitus Condition", not "Infant, Toddler & Youth Room", "Snoring",
and "Tinnitus" as originally guessed.

One genuine wrinkle, not a mistake: `Blanket.generateBlanketName()`'s
confirmed string for the *same* Kids room type is "Infant, Toddler &
Youth Room Blanket" — a third variant, different again from both the
picker label above and the "Infant, Toddler & Kids Room Blanket"
wording seen in the app screenshot referenced earlier in this document.
The vendor is genuinely inconsistent about this one room type's name
across its own screens. `protocol.py` keeps both meanings distinct
rather than collapsing them: `ROOM_TYPE_LABELS` for the picker (what
you choose *from* — used as the select entity's options) and
`BLANKET_NAMES` for the resulting blanket's full name (what the app
displays once one's active — used for `BEDROOM_BLANKETS`/Now Playing).

Implemented as two select entities (`RoomType`/`RoomStyle` enums,
`encode_blanket`/`decode_blanket` in `protocol.py`, mirroring
`Blanket.getBlanketIndex()`'s arithmetic) rather than the original flat
select: **Sleep Blanket Room Type** and **Sleep Blanket Surface Type**.
Both read and write the same combined `SLEEP_SOUND_TRACK_UUID` value —
changing one re-reads the characteristic first so the other dimension's
current setting isn't clobbered, rather than assuming a cached value.

## Extracting Compiled Resources, Not Just Decompiled Source

`jadx` (used for everything else in this document) only decompiles
`classes.dex` back to Java source — it doesn't extract the compiled
resource table (`resources.arsc`), so any string/array/color *resource*
referenced by ID (`R.string.foo`, `R.array.bar`) was previously only
inferable from the resource's ID name, not its actual rendered value.
`androguard` (a pure-Python APK analysis library, `pip install
androguard`) reads `resources.arsc` directly and can resolve any
resource ID to its real compiled value:

```python
from androguard.core.apk import APK
apk = APK("nightingale.apk")
ar = apk.get_android_resources()
pkg = ar.get_packages_names()[0]
res_id = ar.get_res_id_by_key(pkg, "array", "lightColors")
ar.get_resolved_res_configs(res_id)  # -> the actual array contents
```

This is how the Light Color palette and the five Room Type picker
labels below went from "confirmed by naming" or "inferred" to
byte-for-byte confirmed. Worth reaching for any time a characteristic's
options are documented as "inferred from resource-id naming" — that
phrase specifically means jadx-only decompilation couldn't confirm the
exact text, which `androguard` usually can.

## Confirmed: Light Color Is Exactly 4 Colors — Not an Integration Limitation

`LIGHT_COLOR_UUID` is a 3-byte RGB characteristic — nothing about the
wire format limits it to a handful of presets, so it was a fair
question whether White/Green/Blue/Red was the complete native palette
or just what this integration happened to implement. Traced to
`RoomSettingsViewModel.loadColors()`, which populates the app's own
color picker from `Application.getContext().getResources()
.getIntArray(R.array.lightColors)` — a genuine Android resource array,
extracted directly from the compiled resource table:

```
R.array.lightColors = [0xFFFFFFFF, 0xFFFF0000, 0xFF00FF00, 0xFF0000FF]
```

Four entries, exactly White/Red/Green/Blue (Android's `0xAARRGGBB`
format; alpha is always `0xFF`/opaque, irrelevant to the 3-byte BLE
format). This is the app's **entire** palette — confirmed by the
array's real length, not a limitation of this integration's own
`LIGHT_COLOR_PRESETS`. Also promotes "Red" from inferred to confirmed:
it was previously only pattern-matched as the logical fourth primary,
never actually seen in the app's own resources until this extraction.

The 4-color limit is purely a software choice, not evidence either way
about the firmware: `LeNightingaleDevice.setLightColor(Integer)` is a
hardcoded `switch` on a button index (1-4) that picks one of exactly
four literal byte arrays — there's no code path anywhere in the app
that could ever construct or send a fifth color. Unlike Volume/Ramp,
there's no app-side range check here that would at least imply a known
device-side constraint.

Live-tested directly (`tools/light_color_probe.py`,
`tools/light_color_set.py`) against a physical unit: the device
accepts and stores **any** 3-byte RGB value — every write read back
byte-for-byte identical, for both preset and non-preset colors. Pure
single-channel values at reduced intensity (`80 00 00`, `00 80 00`,
`00 00 80`) all rendered as correctly-colored, appropriately dimmer
red/green/blue, confirming the R/G/B byte order itself is right.

However, two-channel blends with a large green component alongside red
rendered visibly wrong: `FF 80 00` (intended orange) looked greenish,
and `FF C0 80` (intended warm white) looked light blue. Since pure
channels and roughly-balanced blends (purple, cyan) all rendered
correctly, this isn't a byte-order bug — a real channel swap would
also break the already-confirmed pure presets, and it doesn't. The
likely explanation is mundane: an uncorrected, unbalanced RGB LED,
where the green die is disproportionately bright relative to red at
moderate-to-high duty cycles (a common trait of cheap RGB LEDs without
a gamma/channel-correction curve applied), not anything wrong with the
protocol. Full arbitrary-RGB support is real and usable, but a color
picker exposing raw RGB should not be assumed to render visually
faithful colors for every blend, particularly warm/orange tones with a
substantial red-plus-green mix.

## Known Vendor Bug: Page Volume UUID (Recovered, Not a Dead End)

`ngVolumePageUUID` in `NightingaleGatt.java` (line 55) is declared as:

```java
public static final UUID ngVolumePageUUID = UUID.fromString("f2e85c5e6-97a4-4c3a-9742-5278bf3881ec");
```

That string has 9 hex digits in its first group instead of 8 — not a
valid UUID; `UUID.fromString()` throws `IllegalArgumentException` on it.
That part still stands as a genuine vendor bug in `NightingaleGatt.java`.

**But** with a local decompiled source copy to search further, a second,
independent declaration of the same conceptual constant turned up in
`bluerocket/cgm/domain/BleManager.java` (line 129), correctly formed:

```java
private static final UUID ngVolumePageUUID = UUID.fromString("2e85c5e6-97a4-4c3a-9742-5278bf3881ec");
```

Same value, just missing the stray leading `f` — so the real UUID *is*
recoverable after all, contrary to the original "unimplementable" call
in this section. Whether the shipped app itself ever worked here is a
separate question: the runtime device class, `LeNightingaleDevice.java`,
references `NightingaleGatt.ngVolumePageUUID` (the broken one), not
`BleManager`'s correct copy, so the live app likely hit this same bug in
production. `BleManager.java` appears to be a separate/older Bluetooth
manager not on that path.

There's also a sibling UUID this repo never had at all: `ngSoundPageUUID
= 6500a2cd-6b0d-494a-af32-878b5bfa45cd`, valid and unbroken. Together,
`ngSoundPageUUID`/`ngVolumePageUUID` aren't a third ongoing listening
mode alongside Sleep/Relax — `SoundTestGattCallback.java`'s handling
(`"Sound Played"` / `"Volume Updated"` status messages, used from
`DeviceSetupTestFragmentVF`) confirms this is a **one-shot test-tone
pair used during device setup/verification**, not part of normal
operation. Not worth wiring into a persistent HA entity even now that
the UUID is known — but worth correcting the record: this wasn't a dead
end, and the lesson (a bug in one file doesn't mean the same constant is
wrong everywhere it's declared) is worth remembering for anything else
found "broken" here in the future.

## Confirmed: Disable Button, Auto-Schedule Flags, Volume Balance

With a local decompiled source copy available for direct grepping, four
more characteristics moved from unverified guesses to source-traced
confirmations in one pass:

- **Disable physical button**: `setDisableBtn(Integer)` switches on the
  literal values `0`/`1`, writing a plain 1-byte flag — same shape as
  the Status characteristics.
- **Sound scheduled** / **Light scheduled**: called as
  `setSoundScheduled(1)`/`setSoundScheduled(0)` with literal integers
  (`SetSleepScheduleFragment.java`) — confirms the guessed 0x00/0x01
  enable-flag format exactly.
- **Volume balance**: `setBalance(Integer balance)` validates
  `balance >= -10 && balance <= 10` before writing
  `(byte) balance.intValue()` — a **signed** 1-byte value, `-10` to
  `10`, not the unsigned guess originally on record.

All four are now wired up: the three flags as switches (Disable
Physical Button, Sound Auto-Schedule, Light Auto-Schedule), Volume
Balance as a number entity.

## Confirmed vs. Unverified

Entries marked "confirmed" above were traced to an actual byte-construction call site in
the decompiled app (`BigInteger.toByteArray()`, a manual `byte[]`, or a `ByteBuffer` build)
and/or tested live against a physical unit. Entries marked "(unverified)" are inferred
purely from naming and sibling-characteristic pattern-matching — same service, same
apparent single-byte-percentage shape as confirmed neighbors — but haven't been traced to
their construction code or tested live yet. Treat unverified entries as a starting guess,
not a guarantee.

## Multi-Unit Rooms: LeDeviceSync Is a One-Time Clone, Not a Live Pairing

The marketing copy describes sound blankets reflecting "from two
different units, each with 2 speakers" — but there's no special
stereo-mode characteristic or ongoing pairing protocol behind it.
`bluerocket/cgm/device/LeDeviceSync.java` implements the entire feature:
given a master address and a new ("copy") address, it opens BLE
connections to both and, for a fixed list of 18 characteristics, reads
the raw bytes off the master and writes them straight onto the new
unit — no decode/re-encode, just a byte-for-byte passthrough.

It's triggered from exactly one place: `DeviceSetupTestFragmentVF.java`'s
add-a-device wizard, specifically the `NEW_BLE_DEVICE` configuration
path when a room already has a unit configured. It runs once, when the
second unit is onboarded, and never again — after that, each unit is
just an independent device that happened to start with matching
settings. Any change afterward, in the app or over BLE directly,
updates only whichever unit you're actually talking to.

The 18 synced characteristics: Location name, Room name, Sleep sound
track (Blanket), Sound status, Light status, Sound Mute, Sleep Volume,
Light Level, Sound/Light Scheduled flags, Light Color, all four
schedule times, Sound Mode, Relax Sound Track, Relax Volume. Notably
**not** synced: Volume Balance, Disable Button, Ramp — balance makes
sense to exclude (L/R skew is about a specific unit's physical
placement, not something that should transfer to a second unit
elsewhere in the room); no evidence either way on why the other two
aren't included.

Implemented as an opt-in config flow step (`config_flow.py`'s
`copy_settings` step, `sync.py`'s `async_copy_settings`), matching the
app's own one-time-clone behavior exactly, including the raw
byte-passthrough approach — see README.md, "Adding a second unit."

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
