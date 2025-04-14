"""Husqvarna Automower BLE lawn mower entity."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HusqvarnaAutomowerBleEntity, HusqvarnaCoordinator

_LOGGER = logging.getLogger(__name__)

FEATURES = (
    LawnMowerEntityFeature.PAUSE
    | LawnMowerEntityFeature.START_MOWING
    | LawnMowerEntityFeature.DOCK
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AutomowerLawnMower integration from a config entry."""
    coordinator: HusqvarnaCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    model = coordinator.model
    address = coordinator.address

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        [
            AutomowerLawnMower(
                coordinator,
                f"automower_{model}_{address}",
                model,
                FEATURES,
            ),
        ]
    )


class AutomowerLawnMower(HusqvarnaAutomowerBleEntity, LawnMowerEntity):
    """Husqvarna Automower."""

    def __init__(
        self,
        coordinator: HusqvarnaCoordinator,
        unique_id: str,
        name: str,
        features: LawnMowerEntityFeature = LawnMowerEntityFeature(0),
    ) -> None:
        """Initialize the lawn mower."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_supported_features = features
        self._attr_activity = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            manufacturer=coordinator.manufacturer,
            model=coordinator.model,
        )

    def _get_activity(self) -> LawnMowerActivity | None:
        """Return the current lawn mower activity."""
        if not self.coordinator.data:
            _LOGGER.warning("Coordinator data is unavailable")
            return None

        state = self.coordinator.data.get("state")
        activity = self.coordinator.data.get("activity")

        _LOGGER.debug(f"Mower state: {state}, Mower activity: {activity}")

        if state is None or activity is None:
            return None

        match str(state):
            case "5":
                return LawnMowerActivity.PAUSED
            case "2" | "0" | "1":
                return LawnMowerActivity.ERROR
            case "7" | "6" | "4":
                match str(activity):
                    case "1" | "5":
                        return LawnMowerActivity.DOCKED
                    case "2" | "3":
                        return LawnMowerActivity.MOWING
                    case "4":
                        return LawnMowerActivity.RETURNING
                    case "6":
                        return LawnMowerActivity.ERROR
        return LawnMowerActivity.ERROR

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Handling coordinator update for AutomowerLawnMower")
        self._update_attr()
        super()._handle_coordinator_update()

    @callback
    def _update_attr(self) -> None:
        """Update mower attributes."""
        self._attr_activity = self._get_activity()
        self._attr_available = self._attr_activity is not None

    async def async_start_mowing(self) -> None:
        """Start mowing."""
        _LOGGER.debug("Starting mower")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_resume()
        if self._attr_activity == LawnMowerActivity.DOCKED:
            await self.coordinator.mower.mower_override()
        await self.coordinator.async_request_refresh()

        self._attr_activity = self._get_activity()
        self.async_write_ha_state()

    async def async_dock(self) -> None:
        """Start docking."""
        _LOGGER.debug("Docking mower")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_park()
        await self.coordinator.async_request_refresh()

        self._attr_activity = self._get_activity()
        self.async_write_ha_state()

    async def async_pause(self) -> None:
        """Pause mower."""
        _LOGGER.debug("Pausing mower")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_pause()
        await self.coordinator.async_request_refresh()

        self._attr_activity = self._get_activity()
        self.async_write_ha_state()

    async def _ensure_connected(self) -> bool:
        """Ensure the mower is connected."""
        if self.coordinator.mower.is_connected():
            return True

        _LOGGER.debug("Attempting to connect to mower")
        device = bluetooth.async_ble_device_from_address(
            self.coordinator.hass, self.coordinator.address, connectable=True
        )
        if not device:
            _LOGGER.error("Failed to find BLE device for mower")
            return False

        if not await self.coordinator.mower.connect(device):
            _LOGGER.error("Failed to connect to mower")
            return False

        return True
