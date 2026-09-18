"""Config flow for Nightingale.

Two physical units (one per room) means two config entries, each keyed by
its own MAC address as the unique_id — this flow is written so it can run
twice, once per device.
"""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_ROOM_NAME, DOMAIN

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class NightingaleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a single Nightingale unit."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a unit discovered via the manifest's service-UUID matcher."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered unit and ask which room it's in."""
        assert self._discovery_info is not None
        discovery_info = self._discovery_info

        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_ROOM_NAME],
                data={CONF_ADDRESS: discovery_info.address},
            )

        default_name = discovery_info.name or discovery_info.address
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_ROOM_NAME, default=default_name): str}
            ),
            description_placeholders={
                "name": default_name,
                "address": discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual entry — MAC address plus a room label.

        Manual entry is the primary path here: the advertised local_name
        for the NG2000 hasn't been confirmed yet, so the bluetooth matcher
        in manifest.json only matches on the service UUID, and discovery
        may not surface every unit. Both known units' MAC addresses are
        already known from live testing, so typing them in directly is
        reliable regardless of discovery.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not _MAC_RE.match(address):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_ROOM_NAME],
                    data={CONF_ADDRESS: address},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_ROOM_NAME): str,
                }
            ),
            errors=errors,
        )
