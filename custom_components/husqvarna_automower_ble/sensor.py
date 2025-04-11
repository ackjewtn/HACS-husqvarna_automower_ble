"""Support for Husqvarna BLE sensors."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from automower_ble.protocol import ModeOfOperation, MowerState, MowerActivity

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN, MANUFACTURER
from .coordinator import HusqvarnaCoordinator

_LOGGER = logging.getLogger(__name__)

MOWER_SENSORS = [
    SensorEntityDescription(
        name="Battery Level",
        key="battery_level",
        unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=None,
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        name="Next Start Time",
        key="next_start_time",
        unit_of_measurement=None,
        device_class=None,
        state_class=None,
        entity_category=None,
        icon="mdi:timer",
    ),
    SensorEntityDescription(
        name="Mode",
        key="mode",
        unit_of_measurement=None,
        device_class=None,
        state_class=None,
        entity_category=None,
        icon="mdi:robot",
    ),
    SensorEntityDescription(
        name="State",
        key="state",
        unit_of_measurement=None,
        device_class=None,
        state_class=None,
        entity_category=None,
        icon="mdi:state-machine",
    ),
    SensorEntityDescription(
        name="Activity",
        key="activity",
        unit_of_measurement=None,
        device_class=None,
        state_class=None,
        entity_category=None,
        icon="mdi:run",
    ),
    SensorEntityDescription(
        name="Total running time",
        key="totalRunningTime",
        unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer",
    ),
    SensorEntityDescription(
        name="Total cutting time",
        key="totalCuttingTime",
        unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer",
    ),
    SensorEntityDescription(
        name="Remaining Charge Time",
        key="RemainingChargingTime",
        unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:power-plug-battery",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AutomowerLawnMower sensor from a config entry."""
    coordinator: HusqvarnaCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug("Creating mower sensors")
    sensors = [
        AutomowerSensorEntity(
            coordinator, description, "automower_" + format_mac(coordinator.address)
        )
        for description in MOWER_SENSORS
    ]
    if not sensors:
        _LOGGER.error("No sensors were created. Check MOWER_SENSORS.")
    async_add_entities(sensors)


class AutomowerSensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of an Automower sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HusqvarnaCoordinator,
        description: SensorEntityDescription,
        mower_id: str,
    ) -> None:
        """Initialize the Automower sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{mower_id}_{description.key}"
        self._attributes = {"description": description.name, "last_updated": None}

        _LOGGER.debug(
            "Creating sensor entity: %s with unique_id: %s",
            self.entity_description.name,
            self._attr_unique_id,
        )

    @property
    def state(self):
        """Return the state of the sensor."""
        value = self._update_attr()
        if self.entity_description.key == "mode":
            return ModeOfOperation(value).name if value is not None else None
        if self.entity_description.key == "state":
            return MowerState(value).name if value is not None else None
        if self.entity_description.key == "activity":
            return MowerActivity(value).name if value is not None else None
        return value

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        last_update = self.coordinator._last_successful_update
        if last_update is None:
            return False
        return datetime.now() - last_update < timedelta(hours=1)

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        return self._attributes

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator update."""
        self._update_attr()
        super()._handle_coordinator_update()

    def _update_attr(self) -> None:
        """Update attributes for the sensor."""
        try:
            self._attr_native_value = self.coordinator.data[self.entity_description.key]
            self._attr_available = self._attr_native_value is not None
            _LOGGER.debug(
                "Updated sensor %s with value %s",
                self.entity_description.key,
                self._attr_native_value,
            )
        except KeyError:
            _LOGGER.warning(
                "Key %s not found in coordinator data. Attempting deep search.",
                self.entity_description.key,
            )
            self._deep_search()

        return self._attr_native_value

    def _deep_search(self) -> None:
        """Perform a deep search for the attribute in nested data."""
        try:
            stats_dict = self.coordinator.data.get("statistics", {})
            self._attr_native_value = stats_dict.get(self.entity_description.key)
            self._attr_available = self._attr_native_value is not None
            if self._attr_native_value is not None:
                _LOGGER.debug(
                    "Deep search successful for key %s with value %s",
                    self.entity_description.key,
                    self._attr_native_value,
                )
            else:
                _LOGGER.error(
                    "Deep search failed for key %s. Value not found.",
                    self.entity_description.key,
                )
        except Exception as ex:
            _LOGGER.exception(
                "Unexpected error during deep search for key %s: %s",
                self.entity_description.key,
                ex,
            )

    @property
    def device_info(self) -> dict:
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.serial)},
            "manufacturer": MANUFACTURER,
            "model": self.coordinator.model,
        }
