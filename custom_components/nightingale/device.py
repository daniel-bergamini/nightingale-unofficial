"""BLE transport for a Nightingale unit.

Wraps bleak-retry-connector so that Nightingale entities never talk to
BleakClient directly. Connections are resolved through Home Assistant's
Bluetooth integration (bluetooth.async_ble_device_from_address), so they
route through whichever adapter or ESPHome Bluetooth Proxy currently has
the device in range — never a locally opened BleakScanner/BleakClient.

This module is transport only: raw GATT read/write/notify by
characteristic UUID. Byte-format encode/decode lives in protocol.py.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
    retry_bluetooth_connection_error,
)
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

NotifyCallback = Callable[[bytes], None]

# No bleak/proxy operation below is guaranteed to time out on its own --
# confirmed the hard way when a notify subscription over an ESPHome
# proxy hung indefinitely and blocked config entry setup entirely (HA
# awaits each entity's async_added_to_hass as part of platform setup).
# Every read/write/notify call is wrapped so a hang becomes a catchable
# BleakError instead of blocking forever.
BLE_OPERATION_TIMEOUT = 10


class NightingaleNotFoundError(Exception):
    """Raised when the address isn't currently seen by any adapter/proxy."""


class NightingaleDevice:
    """Manages a single BLE connection to one Nightingale unit."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self._client: BleakClientWithServiceCache | None = None
        self._connect_lock = asyncio.Lock()
        # Guards _active_notify_uuids/_notify_unsupported and the actual
        # client.start_notify() call. Without this, two entities sharing
        # one characteristic (first happened in 0.7.0: Sleep Blanket Room
        # Type and Surface Type both notify on SLEEP_SOUND_TRACK_UUID) can
        # race async_start_notify() concurrently and both decide the
        # subscription hasn't started yet, issuing two simultaneous
        # notify-enable requests for the same characteristic -- which
        # hung the underlying connection badly enough that even this
        # module's own per-operation timeouts couldn't recover it, only
        # a fresh connection (e.g. via a completely separate client) did.
        self._notify_lock = asyncio.Lock()
        self._notify_callbacks: dict[str, list[NotifyCallback]] = {}
        self._active_notify_uuids: set[str] = set()
        # Characteristics that raised BleakError on start_notify (e.g. no
        # NOTIFY/INDICATE property) — skip retrying these, they can still
        # be read/written directly, just not subscribed to.
        self._notify_unsupported: set[str] = set()

    @property
    def ble_device(self) -> BLEDevice | None:
        """Return the current BLEDevice, or None if not currently seen.

        Resolved fresh on every call — this can come from a different
        adapter/proxy than the last connection if the previous one lost
        the device.
        """
        return bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )

    @property
    def available(self) -> bool:
        """Return True if some adapter/proxy currently sees this device."""
        return self.ble_device is not None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _disconnected_callback(self, client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("%s: disconnected", self.address)
        if self._client is client:
            self._client = None

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return self._client
            ble_device = self.ble_device
            if ble_device is None:
                raise NightingaleNotFoundError(
                    f"{self.address} not visible to any Bluetooth adapter or proxy"
                )
            _LOGGER.debug("%s: connecting", self.address)
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.address,
                disconnected_callback=self._disconnected_callback,
            )
            self._client = client
            self._active_notify_uuids = set()
            await self._resubscribe_notifications(client)
            return client

    async def _resubscribe_notifications(
        self, client: BleakClientWithServiceCache
    ) -> None:
        """Re-arm notify subscriptions lost on the previous disconnect."""
        async with self._notify_lock:
            for char_uuid, callbacks in self._notify_callbacks.items():
                if not callbacks or char_uuid in self._notify_unsupported:
                    continue
                try:
                    async with asyncio.timeout(BLE_OPERATION_TIMEOUT):
                        await client.start_notify(
                            char_uuid, self._make_notify_handler(char_uuid)
                        )
                except (BleakError, TimeoutError):
                    _LOGGER.warning(
                        "%s: %s does not support notifications; will only "
                        "reflect state on read/write",
                        self.address,
                        char_uuid,
                        exc_info=True,
                    )
                    self._notify_unsupported.add(char_uuid)
                    continue
                self._active_notify_uuids.add(char_uuid)

    def _make_notify_handler(self, char_uuid: str) -> Callable[[object, bytearray], None]:
        def _handler(_sender: object, data: bytearray) -> None:
            for callback in list(self._notify_callbacks.get(char_uuid, [])):
                callback(bytes(data))

        return _handler

    async def async_connect(self) -> None:
        """Establish (or confirm) the connection."""
        await self._ensure_connected()

    async def async_disconnect(self) -> None:
        async with self._connect_lock:
            if self._client is not None:
                await self._client.disconnect()
                self._client = None

    @retry_bluetooth_connection_error()
    async def async_read_gatt(self, char_uuid: str) -> bytes:
        """Read a characteristic's raw bytes.

        Raises plain TimeoutError (not wrapped as BleakError) on timeout:
        bleak_retry_connector deliberately excludes TimeoutError from what
        @retry_bluetooth_connection_error retries, specifically so a
        caller-imposed timeout isn't multiplied across retry attempts.
        Wrapping it as BleakError here would defeat that on purpose.
        """
        client = await self._ensure_connected()
        async with asyncio.timeout(BLE_OPERATION_TIMEOUT):
            return bytes(await client.read_gatt_char(char_uuid))

    @retry_bluetooth_connection_error()
    async def async_write_gatt(
        self, char_uuid: str, data: bytes, response: bool = True
    ) -> None:
        """Write a characteristic's raw bytes. See async_read_gatt re: timeout."""
        client = await self._ensure_connected()
        async with asyncio.timeout(BLE_OPERATION_TIMEOUT):
            await client.write_gatt_char(char_uuid, data, response=response)

    async def async_start_notify(
        self, char_uuid: str, callback: NotifyCallback
    ) -> None:
        """Subscribe to notifications on a characteristic.

        `callback` receives the raw bytes of each notification.
        """
        callbacks = self._notify_callbacks.setdefault(char_uuid, [])
        callbacks.append(callback)
        # _ensure_connected() may have just (re)connected, in which case it
        # already re-armed every uuid with a callback — including this one,
        # since we appended above before calling it. Only start it here if
        # that didn't just happen, to avoid double-subscribing.
        client = await self._ensure_connected()
        async with self._notify_lock:
            if char_uuid in self._notify_unsupported:
                return
            if char_uuid not in self._active_notify_uuids:
                try:
                    async with asyncio.timeout(BLE_OPERATION_TIMEOUT):
                        await client.start_notify(
                            char_uuid, self._make_notify_handler(char_uuid)
                        )
                except (BleakError, TimeoutError):
                    _LOGGER.warning(
                        "%s: %s does not support notifications; will only "
                        "reflect state on read/write",
                        self.address,
                        char_uuid,
                        exc_info=True,
                    )
                    self._notify_unsupported.add(char_uuid)
                    return
                self._active_notify_uuids.add(char_uuid)

    async def async_stop_notify(self, char_uuid: str, callback: NotifyCallback) -> None:
        """Unsubscribe a single callback from a characteristic's notifications."""
        callbacks = self._notify_callbacks.get(char_uuid)
        if not callbacks or callback not in callbacks:
            return
        callbacks.remove(callback)
        if callbacks:
            return
        self._active_notify_uuids.discard(char_uuid)
        if self._client is None or not self._client.is_connected:
            return
        try:
            async with asyncio.timeout(BLE_OPERATION_TIMEOUT):
                await self._client.stop_notify(char_uuid)
        except (BleakError, TimeoutError):
            _LOGGER.debug(
                "%s: stop_notify failed for %s (already disconnected?)",
                self.address,
                char_uuid,
                exc_info=True,
            )
