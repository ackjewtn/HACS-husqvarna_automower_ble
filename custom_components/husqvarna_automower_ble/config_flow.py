"""Config flow for Husqvarna Bluetooth integration."""

from __future__ import annotations

import logging
import random
from typing import Any

from husqvarna_automower_ble.mower import Mower
from bleak import BleakError
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, CONF_ADDRESS, CONF_PIN, CONF_CLIENT_ID

_LOGGER = logging.getLogger(__name__)


def _is_supported(discovery_info: BluetoothServiceInfo) -> bool:
    """Check if the discovered device is supported."""
    _LOGGER.debug(
        "Checking if device %s is supported. Manufacturer data: %s",
        discovery_info.address,
        discovery_info.manufacturer_data,
    )
    return any(key == 1062 for key in discovery_info.manufacturer_data)


class HusqvarnaAutomowerBleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Husqvarna Bluetooth."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.address: str | None = None
        self.pin: int | None = None
        _LOGGER.debug("Initializing Husqvarna Bluetooth config flow")

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> ConfigFlowResult:
        """Handle the Bluetooth discovery step."""
        _LOGGER.debug("Discovered Bluetooth device: %s", discovery_info)

        if not _is_supported(discovery_info):
            _LOGGER.debug("Device %s is not supported", discovery_info.address)
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

        if not hasattr(self, "address"):
            self.address = ""

        errors = {}
        if user_input is not None:
            self.address = user_input[CONF_ADDRESS]
            self.pin = user_input[CONF_PIN]

            # Validate the Bluetooth address and PIN
            if not self.address:
                errors["base"] = "invalid_address"
            elif not isinstance(self.pin, int) or self.pin < 0:
                errors["base"] = "invalid_pin"
            else:
                # Attempt to connect to the mower and validate it
                device = bluetooth.async_ble_device_from_address(
                    self.hass, self.address, connectable=True
                )
                channel_id = random.randint(1, 0xFFFFFFFF)

                try:
                    mower = Mower(channel_id, self.address, self.pin)
                    manufacture, device_type, model = await mower.probe_gatts(device)
                except (BleakError, TimeoutError) as exception:
                    _LOGGER.error(
                        "Failed to connect to device at %s: %s", self.address, exception
                    )
                    errors["base"] = "cannot_connect"
                except Exception as ex:
                    _LOGGER.exception("Unexpected error: %s", ex)
                    errors["base"] = "exception"
                else:
                    # Create the configuration entry
                    title = f"{manufacture} {device_type.replace(chr(0), '')}"
                    _LOGGER.info("Successfully discovered device: %s", title)
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_ADDRESS: self.address,
                            CONF_CLIENT_ID: channel_id,
                            CONF_PIN: self.pin,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS, default=self.address): str,
                    vol.Optional(CONF_PIN, default=0): int,
                },
            ),
            errors=errors,
        )
