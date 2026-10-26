"""Sensors for DIVERA 24/7 alarms and vehicles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Alarm, Vehicle
from .coordinator import DiveraConfigEntry, DiveraUnitCoordinator
from .entity import DiveraUnitEntity, DiveraVehicleEntity, async_setup_vehicle_entities

PARALLEL_UPDATES = 0

# Home Assistant states are limited to 255 characters
MAX_STATE_LENGTH = 255

type StateValue = str | int | datetime | None


@dataclass(frozen=True, kw_only=True)
class DiveraAlarmSensorDescription(SensorEntityDescription):
    """Describes a sensor showing a field of the latest alarm."""

    value_fn: Callable[[Alarm], StateValue]
    attr_fn: Callable[[Alarm], dict[str, Any]] | None = None


@dataclass(frozen=True, kw_only=True)
class DiveraVehicleSensorDescription(SensorEntityDescription):
    """Describes a sensor of a vehicle."""

    value_fn: Callable[[Vehicle], StateValue]


ALARM_SENSORS: tuple[DiveraAlarmSensorDescription, ...] = (
    DiveraAlarmSensorDescription(
        key="alarm_title",
        translation_key="alarm_title",
        value_fn=lambda alarm: alarm.title or None,
    ),
    DiveraAlarmSensorDescription(
        key="alarm_text",
        translation_key="alarm_text",
        value_fn=lambda alarm: alarm.text or None,
        # The state is truncated, the attribute holds the full message
        attr_fn=lambda alarm: {"full_text": alarm.text},
    ),
    DiveraAlarmSensorDescription(
        key="alarm_address",
        translation_key="alarm_address",
        value_fn=lambda alarm: alarm.address or None,
    ),
    DiveraAlarmSensorDescription(
        key="alarm_date",
        translation_key="alarm_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda alarm: alarm.date,
    ),
    DiveraAlarmSensorDescription(
        key="alarm_vehicles",
        translation_key="alarm_vehicles",
        value_fn=lambda alarm: ", ".join(alarm.vehicles) or None,
        attr_fn=lambda alarm: {"vehicles": alarm.vehicles},
    ),
    DiveraAlarmSensorDescription(
        key="alarm_id",
        translation_key="alarm_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda alarm: alarm.id,
    ),
)

FMS_STATES = [str(status) for status in range(10)]

VEHICLE_SENSORS: tuple[DiveraVehicleSensorDescription, ...] = (
    DiveraVehicleSensorDescription(
        key="fms_status",
        translation_key="fms_status",
        device_class=SensorDeviceClass.ENUM,
        options=FMS_STATES,
        value_fn=lambda vehicle: (
            None if vehicle.fms_status is None else str(vehicle.fms_status)
        ),
    ),
    DiveraVehicleSensorDescription(
        key="fms_note",
        translation_key="fms_note",
        value_fn=lambda vehicle: vehicle.note or None,
    ),
    DiveraVehicleSensorDescription(
        key="fms_time",
        translation_key="fms_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda vehicle: vehicle.status_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiveraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for all units and their vehicles."""
    async_add_entities(
        DiveraAlarmSensor(coordinator, description)
        for coordinator in entry.runtime_data.values()
        for description in ALARM_SENSORS
    )
    async_setup_vehicle_entities(
        entry,
        async_add_entities,
        lambda coordinator, vehicle_id: (
            DiveraVehicleSensor(coordinator, vehicle_id, description)
            for description in VEHICLE_SENSORS
        ),
    )


def _limit(value: StateValue) -> StateValue:
    if isinstance(value, str) and len(value) > MAX_STATE_LENGTH:
        return value[: MAX_STATE_LENGTH - 1] + "…"
    return value


class DiveraAlarmSensor(DiveraUnitEntity, SensorEntity):
    """A field of the newest alarm of the unit, open or closed; unknown if there is none."""

    entity_description: DiveraAlarmSensorDescription

    def __init__(
        self,
        coordinator: DiveraUnitCoordinator,
        description: DiveraAlarmSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateValue:
        """Return the state."""
        alarm = self.coordinator.data.alarm
        return _limit(self.entity_description.value_fn(alarm)) if alarm else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return attributes that don't fit the state."""
        alarm = self.coordinator.data.alarm
        attr_fn = self.entity_description.attr_fn
        return attr_fn(alarm) if alarm and attr_fn else None


class DiveraVehicleSensor(DiveraVehicleEntity, SensorEntity):
    """A sensor of a vehicle."""

    entity_description: DiveraVehicleSensorDescription

    def __init__(
        self,
        coordinator: DiveraUnitCoordinator,
        vehicle_id: int,
        description: DiveraVehicleSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateValue:
        """Return the state."""
        return _limit(self.entity_description.value_fn(self.vehicle))
