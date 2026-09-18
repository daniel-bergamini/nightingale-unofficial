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
| Sleep volume | `6dd68afc-9d26-4e67-95cb-c56c784360e7` | 1 byte, `0x00`–`0x64` (0–100%) |
| Relax volume | `bb23ae19-b2f0-46f4-930d-d89047d92c06` | 1 byte, `0x00`–`0x64` (unverified, pattern-matched to sleep volume) |
| Page volume | ~~`f2e85c5e6-97a4-4c3a-9742-5278bf3881ec`~~ — **invalid, unusable** | 1 byte, `0x00`–`0x64` (unverified) |
| Volume balance (L/R) | `c32f5045-d621-4c9e-8f9b-557b5a5d65cd` | Integer, likely signed for L/R skew (unverified) |
| Sleep sound track | `a54d9906-4298-4656-9bd3-7095e87365d6` | Integer index (unverified — track list not yet enumerated) |
| Relax sound track | `0e4fa979-6e76-45f0-8887-762ee399121c` | Integer index (unverified) |
| Sound scheduled (enable flag) | `86dcd724-031d-4ebe-a2e1-912670a06c3c` | Integer, likely `0x00`/`0x01` (unverified) |
| **Sound auto-on time** ⚠️ not an immediate toggle | `11104650-14be-436b-a900-b72763c3be82` | 2 bytes: `[minute, hour]`, both plain integers, 24hr |
| **Sound auto-off time** ⚠️ not an immediate toggle | `5e6379e1-bd5b-44a2-ac16-74f845d6c388` | 2 bytes: `[minute, hour]`, same format |

### Light

| Name | UUID | Format |
|---|---|---|
| Light level | `adfa5e07-ebe3-4362-ae05-b63cc5aad5b1` | 1 byte, `0x00`–`0x64` (0–100%) |
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
