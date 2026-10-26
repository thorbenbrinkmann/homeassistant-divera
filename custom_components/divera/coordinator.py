"""Data update coordinator for a DIVERA 24/7 unit."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    WEBSOCKET_URL,
    Alarm,
    DiveraApi,
    DiveraAuthError,
    DiveraError,
    DiveraRateLimitError,
    Unit,
    UnitData,
)
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    WS_HEARTBEAT,
    WS_RECONNECT_MAX,
    WS_RECONNECT_MIN,
    WS_REFRESH_EVENTS,
)

_LOGGER = logging.getLogger(__name__)

type DiveraConfigEntry = ConfigEntry[dict[int, DiveraUnitCoordinator]]


class DiveraUnitCoordinator(DataUpdateCoordinator[UnitData]):
    """Loads the data of one unit.

    DIVERA pushes an event over its WebSocket whenever the unit's data changes,
    which triggers a refresh. Polling covers the time the WebSocket is down.
    """

    config_entry: DiveraConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: DiveraConfigEntry,
        api: DiveraApi,
        session: aiohttp.ClientSession,
        unit: Unit,
    ) -> None:
        """Initialize the coordinator."""
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} unit {unit.id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.unit = unit
        # Registry id of the unit's device, set during setup
        self.unit_device_id = ""
        self._session = session
        self._last_alarm_id: int | None = None
        self._paused_until = dt_util.utcnow()
        self._reconnect_delay = WS_RECONNECT_MIN
        # The alarm that arrived with the latest refresh, if it is new and open
        self.new_alarm: Alarm | None = None
        # The alarm that was open before this refresh and is now closed or gone
        self.closed_alarm: Alarm | None = None

    async def _async_update_data(self) -> UnitData:
        if self.data is not None and dt_util.utcnow() < self._paused_until:
            # Rate limited: skip refreshes triggered by WebSocket events as well
            self.new_alarm = None
            self.closed_alarm = None
            return self.data
        try:
            raw = await self.api.pull_all(self.unit.id)
        except DiveraAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DiveraRateLimitError as err:
            self._paused_until = dt_util.utcnow() + timedelta(seconds=err.retry_after)
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except DiveraError as err:
            raise UpdateFailed(str(err)) from err

        previous_alarm = self.data.alarm if self.data is not None else None
        data = UnitData.from_pull_all(raw)
        alarm = data.alarm
        newest_id = alarm.id if alarm else 0
        # The first refresh only records the current alarm, so restarts don't re-trigger it
        last_id = self._last_alarm_id
        self.new_alarm = (
            alarm
            if alarm and last_id is not None and newest_id > last_id and not alarm.closed
            else None
        )
        self.closed_alarm = (
            (alarm if alarm and alarm.id == previous_alarm.id else previous_alarm)
            if previous_alarm
            and not previous_alarm.closed
            and (alarm is None or alarm.closed or alarm.id != previous_alarm.id)
            else None
        )
        self._last_alarm_id = max(last_id or 0, newest_id)
        return data

    async def async_set_user_status(self, status_id: int) -> None:
        """Set the user's own status in this unit."""
        await self.api.set_user_status(self.unit.id, status_id)
        await self.async_request_refresh()

    def start_websocket(self) -> None:
        """Start the WebSocket listener; it is cancelled when the entry unloads."""
        self.config_entry.async_create_background_task(
            self.hass, self._websocket_loop(), f"{DOMAIN} websocket {self.unit.id}"
        )

    async def _websocket_loop(self) -> None:
        while True:
            try:
                await self._websocket_session()
                _LOGGER.debug("WebSocket of unit %s closed", self.unit.id)
            except (DiveraError, aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("WebSocket of unit %s lost: %s", self.unit.id, err)
            _LOGGER.debug(
                "Reconnecting WebSocket of unit %s in %s s",
                self.unit.id,
                self._reconnect_delay,
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, WS_RECONNECT_MAX)

    async def _websocket_session(self) -> None:
        jwt = await self.api.fetch_jwt()
        async with self._session.ws_connect(
            WEBSOCKET_URL, heartbeat=WS_HEARTBEAT
        ) as ws:
            await ws.send_json(self._authenticate_message(jwt))
            async for msg in ws:
                if msg.type is not aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    message: Any = json.loads(msg.data)
                    msg_type = message.get("type") if isinstance(message, dict) else None
                except ValueError:
                    _LOGGER.debug("Ignoring unparsable WebSocket message")
                    continue
                if msg_type == "init":
                    _LOGGER.debug("WebSocket of unit %s authenticated", self.unit.id)
                    self._reconnect_delay = WS_RECONNECT_MIN
                elif msg_type == "jwtExpired":
                    await ws.send_json(
                        self._authenticate_message(await self.api.fetch_jwt())
                    )
                elif msg_type in WS_REFRESH_EVENTS:
                    # Debounced, so a burst of events causes a single request
                    await self.async_request_refresh()
                else:
                    _LOGGER.debug("Ignoring WebSocket event %s", msg_type)

    def _authenticate_message(self, jwt: str) -> dict[str, Any]:
        return {"type": "authenticate", "payload": {"jwt": jwt, "ucr": self.unit.id}}
