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

from .const import CONF_COPY_SETTINGS_FROM, CONF_ROOM_NAME, DOMAIN

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

_NO_COPY = "none"


class NightingaleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a single Nightingale unit."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._pending_address: str | None = None
        self._pending_title: str | None = None

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
            self._pending_address = discovery_info.address
            self._pending_title = user_input[CONF_ROOM_NAME]
            return await self._async_step_after_room_name()

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

        Kept as a fallback alongside auto-discovery (manifest.json now
        matches on both the service UUID and the confirmed local_name,
        "Nightingale"): both known units' MAC addresses are already known
        from live testing, so typing them in directly is reliable even if
        discovery hasn't surfaced a unit yet (e.g. it hasn't advertised
        near a proxy since HA started).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not _MAC_RE.match(address):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._pending_address = address
                self._pending_title = user_input[CONF_ROOM_NAME]
                return await self._async_step_after_room_name()

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

    async def _async_step_after_room_name(self) -> ConfigFlowResult:
        """After address+room name are known, offer to copy settings.

        Mirrors the vendor app's own add-a-second-unit-to-a-room
        behavior (LeDeviceSync.syncDevices(), see sync.py) as a config
        flow choice rather than a silent default. Skipped entirely if
        this is the first Nightingale being configured -- nothing to
        copy from yet.
        """
        if not self._async_current_entries(include_ignore=False):
            return self._async_finish({CONF_ADDRESS: self._pending_address})
        return await self.async_step_copy_settings()

    async def async_step_copy_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optional: clone settings from an already-configured unit."""
        existing = self._async_current_entries(include_ignore=False)

        if user_input is not None:
            data: dict[str, Any] = {CONF_ADDRESS: self._pending_address}
            choice = user_input["copy_from"]
            if choice != _NO_COPY:
                source_entry = next(e for e in existing if e.entry_id == choice)
                data[CONF_COPY_SETTINGS_FROM] = source_entry.data[CONF_ADDRESS]
            return self._async_finish(data)

        options = {_NO_COPY: "Don't copy"} | {
            entry.entry_id: entry.title for entry in existing
        }
        return self.async_show_form(
            step_id="copy_settings",
            data_schema=vol.Schema(
                {vol.Required("copy_from", default=_NO_COPY): vol.In(options)}
            ),
        )

    def _async_finish(self, data: dict[str, Any]) -> ConfigFlowResult:
        assert self._pending_title is not None
        return self.async_create_entry(title=self._pending_title, data=data)
