"""Event entity firing on new DIVERA 24/7 alarms."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Alarm
from .const import EVENT_ALARM_CLOSED, EVENT_NEW_ALARM
from .coordinator import DiveraConfigEntry, DiveraUnitCoordinator
from .entity import DiveraUnitEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiveraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the alarm event for all units."""
    async_add_entities(
        DiveraAlarmEvent(coordinator) for coordinator in entry.runtime_data.values()
    )


def _event_attributes(alarm: Alarm) -> dict[str, Any]:
    return {
        "alarm_id": alarm.id,
        "title": alarm.title,
        "text": alarm.text,
        "address": alarm.address,
        "priority": alarm.priority,
        "latitude": alarm.lat,
        "longitude": alarm.lng,
        "vehicles": alarm.vehicles,
    }


class DiveraAlarmEvent(DiveraUnitEntity, EventEntity):
    """Fires when a new open alarm arrives or when an open alarm is closed."""

    _attr_translation_key = "alarm"
    _attr_event_types = [EVENT_NEW_ALARM, EVENT_ALARM_CLOSED]

    def __init__(self, coordinator: DiveraUnitCoordinator) -> None:
        """Initialize the event entity."""
        super().__init__(coordinator, "alarm_event")

    @callback
    def _handle_coordinator_update(self) -> None:
        if closed := self.coordinator.closed_alarm:
            self._trigger_event(EVENT_ALARM_CLOSED, _event_attributes(closed))
        if alarm := self.coordinator.new_alarm:
            self._trigger_event(EVENT_NEW_ALARM, _event_attributes(alarm))
        super()._handle_coordinator_update()
