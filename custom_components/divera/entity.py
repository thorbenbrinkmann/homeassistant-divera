"""Base entities for the DIVERA 24/7 integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Unit, Vehicle
from .const import DOMAIN
from .coordinator import DiveraConfigEntry, DiveraUnitCoordinator


def unit_identifier(unit_id: int) -> str:
    """Device identifier of a unit."""
    return f"unit_{unit_id}"


def vehicle_identifier(unit_id: int, vehicle_id: int) -> str:
    """Device identifier of a vehicle; scoped to the unit, since UCR ids are per user."""
    return f"vehicle_{unit_id}_{vehicle_id}"


def unit_device_info(unit: Unit) -> DeviceInfo:
    """Device info of a unit."""
    return DeviceInfo(
        identifiers={(DOMAIN, unit_identifier(unit.id))},
        name=unit.name or f"DIVERA 24/7 {unit.id}",
        manufacturer="DIVERA 24/7",
        model="Unit",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://app.divera247.com",
    )


class DiveraUnitEntity(CoordinatorEntity[DiveraUnitCoordinator]):
    """An entity of a unit device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DiveraUnitCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        unit = coordinator.unit
        self._attr_unique_id = f"{unit.id}_{key}"
        self._attr_device_info = unit_device_info(unit)


class DiveraVehicleEntity(CoordinatorEntity[DiveraUnitCoordinator]):
    """An entity of a vehicle device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: DiveraUnitCoordinator, vehicle_id: int, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        unit_id = coordinator.unit.id
        self.vehicle_id = vehicle_id
        self._attr_unique_id = f"{unit_id}_vehicle_{vehicle_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vehicle_identifier(unit_id, vehicle_id))},
            name=self.vehicle.name or f"Vehicle {vehicle_id}",
            manufacturer="DIVERA 24/7",
            model="Vehicle",
            via_device_id=coordinator.unit_device_id,
        )

    @property
    def vehicle(self) -> Vehicle:
        """The current data of the vehicle; only valid while available."""
        return self.coordinator.data.vehicles.get(
            self.vehicle_id, Vehicle(self.vehicle_id, "")
        )

    @property
    def available(self) -> bool:
        """Unavailable once the vehicle is gone from the unit."""
        return super().available and self.vehicle_id in self.coordinator.data.vehicles


def async_setup_vehicle_entities(
    entry: DiveraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[DiveraUnitCoordinator, int], Iterable[Entity]],
) -> None:
    """Add entities for all vehicles, and for vehicles that show up later."""
    for coordinator in entry.runtime_data.values():
        known: set[int] = set()

        @callback
        def add_new(coordinator: DiveraUnitCoordinator = coordinator, known: set[int] = known) -> None:
            new_ids = coordinator.data.vehicles.keys() - known
            if new_ids:
                known.update(new_ids)
                async_add_entities(
                    entity
                    for vehicle_id in sorted(new_ids)
                    for entity in factory(coordinator, vehicle_id)
                )

        add_new()
        entry.async_on_unload(coordinator.async_add_listener(add_new))
