# nightingale-unofficial
Reverse-engineered local BLE control for the Cambridge Sound Management Nightingale sleep system — no app, no cloud, no Ayla dependency.

Protocol details (UUIDs, byte formats, what's confirmed vs. unverified) live in [PROTOCOL.md](PROTOCOL.md). This README covers the Home Assistant custom integration in `custom_components/nightingale/`.

## Status

Implemented: switches (Sound, Light, Sound Mute, Disable Physical Button, Sound Auto-Schedule, Light Auto-Schedule), number sliders (Sleep Volume, Relax Volume, Light Level — all 0–10; Volume Balance — signed -10 to 10), selects (Sound Mode, Light Color, Relax Sound Track — Lakeshore/Crickets/Loons/Whale Songs/Rainstorm, and the Sleep Blanket's two dimensions — Room Type and Surface Type, matching the vendor's own setup wizard rather than one flat 15-item list), sensors (Device Room Name, Device Location Name — the unit's own self-reported strings; Now Playing — a computed summary combining Sound status/Mode/track, mirroring the app's own `getCurrentPlayingString()`), and schedule times (Sound/Light Auto-On/Off Time — the actual times behind the Auto-Schedule switches above), all reflecting live device state via BLE notify where the characteristic supports it, rather than assuming the last command sent.

Known quirk: this device has two distinct sound profiles, selected by the Sound Mode select — **Sleep Volume** is only live when Sound Mode is Sound Blanket, **Relax Volume** only when it's Nature Sound (confirmed via `tools/volume_ab_probe.py` plus live testing in HA). Adjusting the volume that doesn't match the current mode is a no-op, not a bug. See PROTOCOL.md for the full writeup.

Several other characteristics are unverified and intentionally not wired to any entity yet — see PROTOCOL.md.

Connections are proxy-aware: the integration resolves devices through Home Assistant's Bluetooth integration, so it works over an ESPHome Bluetooth Proxy (`bluetooth_proxy: active: true`) exactly the same as a local adapter — it never opens its own scanner or client.

## Requirements

- Home Assistant with the built-in Bluetooth integration enabled, and an adapter or ESPHome Bluetooth Proxy in range of each Nightingale unit.
- File access to your HA config directory (e.g. the Samba, SSH & Terminal, or Studio Code Server add-on on HAOS).
- Each unit's MAC address (get it via `bluetoothctl` or nRF Connect if you don't already have it).

## Installation

Not in the default HACS store — add it as a HACS custom repository:

1. HACS → the **⋮** menu (top right) → **Custom repositories**.
2. Add `https://github.com/daniel-bergamini/nightingale-unofficial`, category **Integration**.
3. Find "Nightingale" in HACS and install it.
4. Restart Home Assistant Core: Settings → System → Restart → **Restart Home Assistant**. This is what makes HA pick up the new component and install its one dependency, `bleak-retry-connector`.
5. Check Settings → System → Logs and search "nightingale" to confirm it loaded without errors.

Future updates then show up in HACS as a normal update notification, tied to this repo's [releases](https://github.com/daniel-bergamini/nightingale-unofficial/releases).

### Installation (manual, without HACS)

1. Copy `custom_components/nightingale/` from this repo into `<config>/custom_components/nightingale/` on your Home Assistant instance.
2. Restart Home Assistant Core the same way as above.
3. Check the logs the same way as above.

## Adding a unit

Repeat once per Nightingale unit (once per room). Two paths, depending on whether HA has already seen the unit advertise:

**Auto-discovered** (a unit has advertised near an HA-connected proxy since HA started): a "Nightingale" card appears under Settings → Devices & Services. Click **Configure**, enter a room name, submit — the MAC address is already filled in from the discovery.

**Manual** (nothing discovered yet, or you'd rather not wait): Settings → Devices & Services → **+ Add Integration** → search "Nightingale" → select it. Enter the unit's MAC address (`AA:BB:CC:DD:EE:FF`) and a room name, submit.

Either way, Home Assistant connects through whichever adapter or proxy currently sees that address, and you end up with one device exposing a full set of entities, all reflecting live state.

**Adding a second unit** (0.10.0+): if you already have a Nightingale configured, the flow adds one more step — "Copy settings from an existing Nightingale?" — mirroring the vendor app's own behavior when adding a second unit to a room (see PROTOCOL.md). It's opt-in (defaults to "Don't copy") and runs once, during this new unit's first setup; it does not keep the two in sync afterward. The source unit's config entry needs to already be loaded (its own connection currently up) for the copy to succeed — if it isn't, the copy is skipped with a warning in the logs rather than failing the new unit's setup.

## Troubleshooting

- **Config entry won't load / retries repeatedly**: confirm the unit is actually advertising and that the nearest ESPHome proxy is online (Settings → Devices & Services → Bluetooth should show it as a connected scanner).
- **Switch doesn't reflect a physical button press**: the entity subscribes to BLE notify on the Status characteristic on setup; if it seems stuck, check the Logs for disconnect/reconnect messages — the underlying connection retries automatically but a prolonged proxy outage will show as `unavailable`.
- **Integration stuck on "Initializing"**: this has happened more than once from different specific causes (a hung notify subscription, then a race between two entities sharing one characteristic), so rather than trust any one fix, there's now a hard backstop: entity setup as a whole times out after 60s (0.7.2+) and reports `ConfigEntryNotReady` instead of hanging forever, and any individual timed-out operation forces a full reconnect rather than reusing a possibly-corrupted connection. If you still see this, it means setup is taking longer than 60s, not that it's stuck indefinitely — check the Logs for what's slow.
- **Reporting a problem** (0.9.0+): Settings → Devices & Services → Nightingale → the unit's device page → ⋮ → **Download Diagnostics** gives a single file with connection state and every entity's current value — usually faster than pasting logs back and forth.
