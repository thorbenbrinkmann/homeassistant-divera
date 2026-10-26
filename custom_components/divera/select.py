"""Select entity for the user's own DIVERA 24/7 status."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DiveraError
from .const import DOMAIN
from .coordinator import DiveraConfigEntry, DiveraUnitCoordinator
from .entity import DiveraUnitEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiveraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the status select for all units."""
    async_add_entities(
        DiveraUserStatusSelect(coordinator)
        for coordinator in entry.runtime_data.values()
    )


class DiveraUserStatusSelect(DiveraUnitEntity, SelectEntity):
    """Your own status in the unit; the options are the unit's status names."""

    _attr_translation_key = "user_status"

    def __init__(self, coordinator: DiveraUnitCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator, "user_status")

    @property
    def options(self) -> list[str]:
        """Return the status names in the unit's sort order."""
        return [status.name for status in self.coordinator.data.user_statuses]

    @property
    def current_option(self) -> str | None:
        """Return the name of the current status."""
        data = self.coordinator.data
        return next(
            (s.name for s in data.user_statuses if s.id == data.user_status_id), None
        )

    async def async_select_option(self, option: str) -> None:
        """Set the status in DIVERA 24/7."""
        status_id = next(
            s.id for s in self.coordinator.data.user_statuses if s.name == option
        )
        try:
            await self.coordinator.async_set_user_status(status_id)
        except DiveraError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_status_failed",
                translation_placeholders={"error": str(err)},
            ) from err
