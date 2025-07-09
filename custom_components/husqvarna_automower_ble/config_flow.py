"""Config flow for Husqvarna Bluetooth integration."""

from __future__ import annotations

import logging
import random
import re
from typing import Any

from bleak_retry_connector import get_device
from husqvarna_automower_ble.mower import Mower
from husqvarna_automower_ble.protocol import ResponseResult
from bleak.exc import BleakError
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, CONF_ADDRESS, CONF_PIN, CONF_CLIENT_ID

_LOGGER = logging.getLogger(__name__)


def _is_valid_bluetooth_address(address: str) -> bool:
    """Validate if the provided string is a valid Bluetooth address format."""
    if not address:
        return False

    # Bluetooth addresses are 6 groups of 2 hex digits separated by colons
    # Format: XX:XX:XX:XX:XX:XX (case insensitive)
    bluetooth_pattern = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
    return bool(re.match(bluetooth_pattern, address))


def _is_supported(discovery_info: BluetoothServiceInfo) -> bool:
    """Check if the discovered device is supported."""

    _LOGGER.debug(
        "Checking if device %s is supported. Manufacturer data: %s",
        discovery_info.address,
        discovery_info.manufacturer_data,
    )

    manufacturer = any(key == 1062 for key in discovery_info.manufacturer_data)
    service_husqvarna = any(
        service == "98bd0001-0b0e-421a-84e5-ddbf75dc6de4"
        for service in discovery_info.service_uuids
    )

    return manufacturer and service_husqvarna


class HusqvarnaAutomowerBleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Husqvarna Bluetooth."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.address: str = ""
        self.pin: int | None = None
        _LOGGER.debug("Initializing Husqvarna Bluetooth config flow")

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> ConfigFlowResult:
        """Handle the Bluetooth discovery step."""

        _LOGGER.debug("Discovered device: %s", discovery_info)
        if not _is_supported(discovery_info):
            return self.async_abort(reason="no_devices_found")

        self.address = discovery_info.address
        await self.async_set_unique_id(self.address)
        self._abort_if_unique_id_configured()
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user input step."""

        _LOGGER.debug("Entering user input step")

        errors = {}
        user_step = self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS, default=self.address): str,
                    vol.Optional(CONF_PIN): int,
                },
            ),
            errors=errors,
        )

        if user_input is not None:
            self.address = user_input[CONF_ADDRESS]
            self.pin = user_input.get(CONF_PIN)
        else:
            return user_step

        # Validate the Bluetooth address and PIN
        if not self.address or not _is_valid_bluetooth_address(self.address):
            errors["base"] = "invalid_address_format"
            return user_step

        if self.pin is not None and (not isinstance(self.pin, int) or self.pin < 0):
            errors["base"] = "invalid_pin_format"
            return user_step

        await self.async_set_unique_id(self.address, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        try:
            device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            ) or await get_device(self.address)

            if not device:
                _LOGGER.error("Device not found: %s", self.address)
                errors["base"] = "device_not_found"
                return user_step

            channel_id = random.randint(1, 0xFFFFFFFF)
            mower = Mower(channel_id, self.address, self.pin)

            # Probe the device
            manufacture, device_type, model = await mower.probe_gatts(device)
            if manufacture is None or device_type is None:
                _LOGGER.error("Failed to probe device %s", self.address)
                errors["base"] = "cannot_connect"
                return user_step

            # Attempt to connect to the device
            response_result = await mower.connect(device)
            if response_result is not ResponseResult.OK:
                _LOGGER.error("Failed to connect to device %s", self.address)
                if (
                    response_result is ResponseResult.INVALID_PIN
                    or response_result is ResponseResult.NOT_ALLOWED
                ):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
                return user_step

            # Disconnect from the device
            await mower.disconnect()

            _LOGGER.debug("Successfully probed and connected to %s", self.address)
        except (BleakError, TimeoutError) as ex:
            _LOGGER.error("Failed to connect to device at %s: %s", self.address, ex)
            errors["base"] = "cannot_connect"
        except Exception as ex:
            _LOGGER.exception("Unexpected error: %s", ex)
            errors["base"] = "exception"
        else:
            # Create the configuration entry
            title = f"{manufacture} {device_type.replace(chr(0), '')}"
            _LOGGER.info("Creating configuration entry with title: %s", title)
            return self.async_create_entry(
                title=title,
                data={
                    CONF_ADDRESS: self.address,
                    CONF_CLIENT_ID: channel_id,
                    CONF_PIN: self.pin,
                },
            )

        return user_step
