"""Binary sensors for DIVERA 24/7 alarms."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Alarm
from .coordinator import DiveraConfigEntry, DiveraUnitCoordinator
from .entity import DiveraUnitEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class DiveraAlarmBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor of a unit's latest alarm."""

    value_fn: Callable[[Alarm | None], bool | None]


BINARY_SENSORS: tuple[DiveraAlarmBinarySensorDescription, ...] = (
    DiveraAlarmBinarySensorDescription(
        key="alarm_active",
        translation_key="alarm_active",
        value_fn=lambda alarm: alarm is not None and not alarm.closed,
    ),
    DiveraAlarmBinarySensorDescription(
        key="alarm_priority",
        translation_key="alarm_priority",
        value_fn=lambda alarm: alarm.priority if alarm else None,
    ),
    DiveraAlarmBinarySensorDescription(
        key="alarm_closed",
        translation_key="alarm_closed",
        value_fn=lambda alarm: alarm.closed if alarm else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiveraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors for all units."""
    async_add_entities(
        DiveraAlarmBinarySensor(coordinator, description)
        for coordinator in entry.runtime_data.values()
        for description in BINARY_SENSORS
    )


class DiveraAlarmBinarySensor(DiveraUnitEntity, BinarySensorEntity):
    """A binary sensor of the unit's alarm state."""

    entity_description: DiveraAlarmBinarySensorDescription

    def __init__(
        self,
        coordinator: DiveraUnitCoordinator,
        description: DiveraAlarmBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data.alarm)
