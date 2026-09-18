# nightingale-unofficial
Reverse-engineered local BLE control for the Cambridge Sound Management Nightingale sleep system — no app, no cloud, no Ayla dependency.

Protocol details (UUIDs, byte formats, what's confirmed vs. unverified) live in [PROTOCOL.md](PROTOCOL.md). This README covers the Home Assistant custom integration in `custom_components/nightingale/`.

## Status

Implemented: power switches (Sound, Light), reflecting live device state via BLE notify rather than assuming the last command sent.

Not yet implemented: sleep volume, light level, sound mode, light color (planned as `number`/`select` entities — the confirmed characteristics are already in `protocol.py`). Several other characteristics are unverified and intentionally not wired to any entity yet — see PROTOCOL.md.

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

Repeat once per Nightingale unit (once per room):

1. Settings → Devices & Services → **+ Add Integration** → search "Nightingale" → select it.

   This opens a manual-entry form rather than an auto-discovered card — the NG2000's advertised `local_name` hasn't been confirmed yet, so the manifest's Bluetooth matcher only matches on the service UUID. Manual entry works reliably regardless, since you already know each unit's MAC address.
2. Enter the unit's MAC address (`AA:BB:CC:DD:EE:FF`) and a room name.
3. Submit. Home Assistant will connect through whichever adapter or proxy currently sees that address.
4. You'll get one device with a Sound switch and a Light switch, both reflecting live state.

## Troubleshooting

- **Config entry won't load / retries repeatedly**: confirm the unit is actually advertising and that the nearest ESPHome proxy is online (Settings → Devices & Services → Bluetooth should show it as a connected scanner).
- **Switch doesn't reflect a physical button press**: the entity subscribes to BLE notify on the Status characteristic on setup; if it seems stuck, check the Logs for disconnect/reconnect messages — the underlying connection retries automatically but a prolonged proxy outage will show as `unavailable`.
