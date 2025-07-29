"""Husqvarna Automower BLE lawn mower entity."""

from __future__ import annotations

import asyncio
import logging

from bleak_retry_connector import get_device
from husqvarna_automower_ble.protocol import MowerActivity, MowerState
from husqvarna_automower_ble.protocol import ResponseResult

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
from homeassistant.helpers import config_validation as cv, entity_platform

from .const import DOMAIN
from .coordinator import HusqvarnaCoordinator
from .entity import HusqvarnaAutomowerBleEntity

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

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "park_indefinitely",
        {},
        "async_park_indefinitely",
    )
    platform.async_register_entity_service(
        "resume_schedule",
        {},
        "async_resume_schedule",
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

        if state == MowerState.PAUSED:
            return LawnMowerActivity.PAUSED
        if state in (MowerState.STOPPED, MowerState.OFF, MowerState.WAIT_FOR_SAFETYPIN):
            # This is actually stopped, but that isn't an option
            return LawnMowerActivity.ERROR
        if state in (
            MowerState.RESTRICTED,
            MowerState.IN_OPERATION,
            MowerState.PENDING_START,
        ):
            if activity in (
                MowerActivity.CHARGING,
                MowerActivity.PARKED,
                MowerActivity.NONE,
            ):
                return LawnMowerActivity.DOCKED
            if activity in (MowerActivity.GOING_OUT, MowerActivity.MOWING):
                return LawnMowerActivity.MOWING
            if activity == MowerActivity.GOING_HOME:
                return LawnMowerActivity.RETURNING
        return LawnMowerActivity.ERROR

    async def async_added_to_hass(self) -> None:
        """Handle when the entity is added to Home Assistant."""
        _LOGGER.debug("AutomowerLawnMower entity added to Home Assistant")
        self._attr_activity = self._get_activity()
        self._attr_available = self._attr_activity is not None and self.available
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Handling coordinator update for AutomowerLawnMower")
        self._attr_activity = self._get_activity()
        self._attr_available = self._attr_activity is not None and self.available
        super()._handle_coordinator_update()

    async def async_start_mowing(self) -> None:
        """Start mowing."""
        _LOGGER.debug("Starting mower")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_resume()
        if self._attr_activity == LawnMowerActivity.DOCKED:
            await self.coordinator.mower.mower_override()

        # Wait a bit longer for the mower to process the command
        await asyncio.sleep(2)

        # Manually disconnect and reconnect to ensure fresh state
        if self.coordinator.mower.is_connected():
            await self.coordinator.mower.disconnect()

        await self.coordinator.async_request_refresh()

        self._attr_activity = self._get_activity()
        self.async_write_ha_state()

    async def async_dock(self) -> None:
        """Start docking."""
        _LOGGER.debug("Docking mower")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_park()

        await asyncio.sleep(2)

        if self.coordinator.mower.is_connected():
            await self.coordinator.mower.disconnect()

        await self.coordinator.async_request_refresh()

        self._attr_activity = self._get_activity()
        self.async_write_ha_state()

    async def async_pause(self) -> None:
        """Pause mower."""
        _LOGGER.debug("Pausing mower")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_pause()

        await asyncio.sleep(2)

        if self.coordinator.mower.is_connected():
            await self.coordinator.mower.disconnect()

        await self.coordinator.async_request_refresh()

        self._attr_activity = self._get_activity()
        self.async_write_ha_state()

    async def async_park_indefinitely(self) -> None:
        """Park mower indefinitely."""
        _LOGGER.debug("Parking mower indefinitely")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_park_indefinitely()

        await asyncio.sleep(2)

        if self.coordinator.mower.is_connected():
            await self.coordinator.mower.disconnect()

        await self.coordinator.async_request_refresh()

        self._attr_activity = self._get_activity()
        self.async_write_ha_state()

    async def async_resume_schedule(self) -> None:
        """Resume mower schedule."""
        _LOGGER.debug("Resuming mower schedule")

        if not await self._ensure_connected():
            return

        await self.coordinator.mower.mower_auto()

        await asyncio.sleep(2)

        if self.coordinator.mower.is_connected():
            await self.coordinator.mower.disconnect()

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
        ) or await get_device(self.coordinator.address)
        if not device:
            _LOGGER.error("Failed to find BLE device for mower")
            return False

        if await self.coordinator.mower.connect(device) is not ResponseResult.OK:
            _LOGGER.error("Failed to connect to mower")
            return False

        return True
