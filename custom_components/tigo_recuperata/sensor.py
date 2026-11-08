"""Single sensor: energy reclaimed today by the Tigo optimizers."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TigoConfigEntry
from .const import CONF_SYSTEM_NAME, DOMAIN
from .coordinator import TigoReclaimedCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TigoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor."""
    async_add_entities([ReclaimedTodaySensor(entry.runtime_data)])


class ReclaimedTodaySensor(CoordinatorEntity[TigoReclaimedCoordinator], SensorEntity):
    """Energy reclaimed today (calendar day), reset by Tigo at midnight.

    No energy device_class on purpose: the sensor is not offered in the
    Energy dashboard. state_class 'measurement' keeps the long-term
    statistics (daily max = reclaimed energy of that day).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "energia_recuperata_oggi"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:solar-power-variant"

    def __init__(self, coordinator: TigoReclaimedCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{coordinator.system_id}_energia_recuperata_oggi"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.system_id))},
            name=f"Tigo {entry.data.get(CONF_SYSTEM_NAME, coordinator.system_id)}",
            manufacturer="Tigo Energy",
            model="Energia recuperata (cloud)",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | None:
        """Return kWh reclaimed today."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data / 1000, 3)
