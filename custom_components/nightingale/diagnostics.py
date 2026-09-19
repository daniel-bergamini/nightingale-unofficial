"""Diagnostics support for Nightingale.

Deliberately does no new device I/O -- just reports the connection
state and whatever HA already knows (entity registry + current state
machine values). This is meant to be fast and side-effect-free, and to
turn a "the integration is stuck/misbehaving" report into a single
downloadable file (Settings -> Devices & Services -> Nightingale -> ...
-> Download Diagnostics) instead of a back-and-forth asking for logs,
version, and current entity states one at a time -- which is exactly
what several real debugging sessions during this integration's
development ended up needing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import NightingaleConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NightingaleConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    device = entry.runtime_data
    registry = er.async_get(hass)
    entity_entries = er.async_entries_for_config_entry(registry, entry.entry_id)

    entities: list[dict[str, Any]] = []
    for entity_entry in entity_entries:
        state = hass.states.get(entity_entry.entity_id)
        entities.append(
            {
                "entity_id": entity_entry.entity_id,
                "unique_id": entity_entry.unique_id,
                "state": state.state if state is not None else None,
                "attributes": dict(state.attributes) if state is not None else None,
            }
        )

    return {
        "address": entry.data.get(CONF_ADDRESS),
        "device_available": device.available,
        "device_connected": device.is_connected,
        "entities": entities,
    }
