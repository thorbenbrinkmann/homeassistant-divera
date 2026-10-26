"""Map positions of DIVERA 24/7 alarms and vehicles."""

from __future__ import annotations

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DiveraConfigEntry, DiveraUnitCoordinator
from .entity import DiveraUnitEntity, DiveraVehicleEntity, async_setup_vehicle_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiveraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up location trackers for all units and their vehicles."""
    async_add_entities(
        DiveraAlarmLocation(coordinator) for coordinator in entry.runtime_data.values()
    )
    async_setup_vehicle_entities(
        entry,
        async_add_entities,
        lambda coordinator, vehicle_id: [
            DiveraVehicleLocation(coordinator, vehicle_id)
        ],
    )


class DiveraAlarmLocation(DiveraUnitEntity, TrackerEntity):
    """Coordinates of the newest alarm."""

    _attr_translation_key = "alarm_location"
    _attr_entity_category = None

    def __init__(self, coordinator: DiveraUnitCoordinator) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, "alarm_location")

    @property
    def latitude(self) -> float | None:
        """Return the latitude."""
        alarm = self.coordinator.data.alarm
        return alarm.lat if alarm and alarm.lng is not None else None

    @property
    def longitude(self) -> float | None:
        """Return the longitude."""
        alarm = self.coordinator.data.alarm
        return alarm.lng if alarm and alarm.lat is not None else None


class DiveraVehicleLocation(DiveraVehicleEntity, TrackerEntity):
    """Position of a vehicle."""

    _attr_translation_key = "vehicle_location"
    _attr_entity_category = None

    def __init__(self, coordinator: DiveraUnitCoordinator, vehicle_id: int) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, vehicle_id, "location")

    @property
    def latitude(self) -> float | None:
        """Return the latitude."""
        vehicle = self.vehicle
        return vehicle.lat if vehicle.lng is not None else None

    @property
    def longitude(self) -> float | None:
        """Return the longitude."""
        vehicle = self.vehicle
        return vehicle.lng if vehicle.lat is not None else None
