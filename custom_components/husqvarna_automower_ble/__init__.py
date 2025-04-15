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

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LAWN_MOWER,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Husqvarna Autoconnect Bluetooth from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    pin: int = entry.data[CONF_PIN]
    channel_id: int = entry.data[CONF_CLIENT_ID]

    LOGGER.info(STARTUP_MESSAGE)

    # Create the Mower instance
    mower = Mower(channel_id, address, pin) if pin != 0 else Mower(channel_id, address)

    # Close stale BLE connections
    await close_stale_connections_by_address(address)

    LOGGER.debug(
        f"Connecting to {address} with channel ID {channel_id} and pin {pin if pin != 0 else 'None'}"
    )
    device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    ) or await get_device(address)

    try:
        if not await mower.connect(device):
            LOGGER.error(f"Failed to connect to device at {address}")
            raise ConfigEntryNotReady("Couldn't find device")
    except (BleakError, TimeoutError) as ex:
        LOGGER.exception(f"Error connecting to device at {address}: {ex}")
        raise ConfigEntryNotReady("Couldn't find device") from ex

    LOGGER.debug("Connected and paired successfully")

    # Retrieve mower details
    try:
        manufacturer = await mower.get_manufacturer()
        model = await mower.get_model()
        serial = await mower.get_serial_number()
        LOGGER.info(f"Connected to Automower: {model} (Serial: {serial})")
    except Exception as ex:
        LOGGER.exception(f"Failed to retrieve mower details: {ex}")
        raise ConfigEntryNotReady("Failed to retrieve mower details") from ex

    # Set up the coordinator
    coordinator = HusqvarnaCoordinator(
        hass, mower, address, manufacturer, model, channel_id, serial
    )

    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator and forward entry setups
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.debug(f"Unloading config entry: {entry.entry_id}")
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: HusqvarnaCoordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            await coordinator.async_shutdown()
        else:
            LOGGER.warning(
                f"Coordinator for entry {entry.entry_id} not found during unload"
            )

    return unload_ok
