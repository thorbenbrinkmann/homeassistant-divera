"""The DIVERA 24/7 integration."""

from __future__ import annotations

import asyncio

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DiveraApi, DiveraAuthError, DiveraError, parse_units, parse_user_name
from .const import CONF_ACCESS_KEY, DOMAIN
from .coordinator import DiveraConfigEntry, DiveraUnitCoordinator
from .entity import unit_device_info, unit_identifier, vehicle_identifier

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: DiveraConfigEntry) -> bool:
    """Set up DIVERA 24/7 from a config entry."""
    session = async_get_clientsession(hass)
    api = DiveraApi(session, entry.data[CONF_ACCESS_KEY])
    try:
        account_data = await api.pull_all()
    except DiveraAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DiveraError as err:
        raise ConfigEntryNotReady(str(err)) from err

    units = parse_units(account_data)
    user_name = parse_user_name(account_data)
    if user_name and entry.title in {*(unit.name for unit in units), "DIVERA 24/7"}:
        hass.config_entries.async_update_entry(entry, title=user_name)

    coordinators = {
        unit.id: DiveraUnitCoordinator(hass, entry, api, session, unit)
        for unit in units
    }
    await asyncio.gather(
        *(c.async_config_entry_first_refresh() for c in coordinators.values())
    )
    entry.runtime_data = coordinators

    # Vehicle devices reference their unit by registry id, so register units first
    device_registry = dr.async_get(hass)
    for coordinator in coordinators.values():
        coordinator.unit_device_id = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id, **unit_device_info(coordinator.unit)
        ).id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    for coordinator in coordinators.values():
        coordinator.start_websocket()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DiveraConfigEntry) -> bool:
    """Unload a config entry; WebSocket tasks are cancelled with it."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: DiveraConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing devices of units or vehicles that no longer exist."""
    current = set()
    for coordinator in entry.runtime_data.values():
        current.add(unit_identifier(coordinator.unit.id))
        current.update(
            vehicle_identifier(coordinator.unit.id, vehicle_id)
            for vehicle_id in coordinator.data.vehicles
        )
    return not any(
        domain == DOMAIN and identifier in current
        for domain, identifier in device.identifiers
    )
