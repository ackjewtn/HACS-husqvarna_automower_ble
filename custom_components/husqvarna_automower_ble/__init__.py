"""The Husqvarna Autoconnect Bluetooth integration."""

from __future__ import annotations

import logging

from husqvarna_automower_ble.mower import Mower
from bleak import BleakError
from bleak_retry_connector import close_stale_connections_by_address, get_device

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, CONF_ADDRESS, CONF_PIN, CONF_CLIENT_ID, STARTUP_MESSAGE
from .coordinator import HusqvarnaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LAWN_MOWER,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Husqvarna Autoconnect Bluetooth from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    pin: int | None = entry.data.get(CONF_PIN)
    channel_id: int = entry.data[CONF_CLIENT_ID]

    _LOGGER.info(STARTUP_MESSAGE)

    def init_mower() -> Mower:
        """Initialize the Mower object."""
        return Mower(channel_id, address, pin)

    mower = await hass.async_add_executor_job(init_mower)

    await close_stale_connections_by_address(address)

    _LOGGER.debug(
        "Connecting to %s with channel ID %s and pin %s", address, channel_id, pin
    )

    try:
        # Attempt to find and connect to the device
        device = bluetooth.async_ble_device_from_address(
            hass, address, connectable=True
        ) or await get_device(address)

        if not device:
            _LOGGER.error("No BLE device found at %s", address)
            raise ConfigEntryNotReady(f"No BLE device found at {address}")

        if not await mower.connect(device):
            _LOGGER.error("Failed to connect to device at %s", address)
            raise ConfigEntryNotReady(f"Failed to connect to device at {address}")
    except (BleakError, TimeoutError) as ex:
        _LOGGER.exception("Error connecting to device at %s: %s", address, ex)
        raise ConfigEntryNotReady(f"Connection error: {ex}") from ex

    _LOGGER.debug("Connected and paired successfully")

    # Retrieve mower details
    try:
        manufacturer = await mower.get_manufacturer()
        model = await mower.get_model()
        serial = await mower.get_serial_number()
        _LOGGER.info("Connected to Automower: %s (Serial: %s)", model, serial)
    except Exception as ex:
        _LOGGER.exception("Failed to retrieve mower details: %s", ex)
        raise ConfigEntryNotReady(f"Failed to retrieve mower details: {ex}") from ex

    # Set up the coordinator
    coordinator = HusqvarnaCoordinator(
        hass, mower, address, manufacturer, model, channel_id, serial
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as ex:
        _LOGGER.exception("Failed to refresh coordinator data: %s", ex)
        raise ConfigEntryNotReady(f"Failed to initialize coordinator: {ex}") from ex

    # Store the coordinator and forward entry setups
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: HusqvarnaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
