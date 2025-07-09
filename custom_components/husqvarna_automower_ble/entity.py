"""Provides the HusqvarnaAutomowerBleEntity."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HusqvarnaCoordinator


class HusqvarnaAutomowerBleEntity(CoordinatorEntity):
    """Coordinator entity for Husqvarna Automower Bluetooth."""

    def __init__(self, coordinator: HusqvarnaCoordinator, context: Any = None) -> None:
        """Initialize coordinator entity."""
        super().__init__(coordinator, context)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if self.coordinator._last_successful_update is None:
            return False
        return datetime.now() - self.coordinator._last_successful_update < timedelta(
            minutes=12
        )
