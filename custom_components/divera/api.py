"""Minimal client for the DIVERA 24/7 REST API v2 (https://api.divera247.com)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import math
from typing import Any

import aiohttp

BASE_URL = "https://app.divera247.com/api/v2/"
WEBSOCKET_URL = "wss://ws.divera247.com/ws"

TIMEOUT = aiohttp.ClientTimeout(total=10)
DEFAULT_RETRY_AFTER = 60
MAX_RETRY_AFTER = 3600


class DiveraError(Exception):
    """Communication with DIVERA 24/7 failed."""


class DiveraAuthError(DiveraError):
    """The access key was rejected."""


class DiveraRateLimitError(DiveraError):
    """DIVERA 24/7 asked to pause requests."""

    def __init__(self, retry_after: int) -> None:
        """Initialize with the pause in seconds."""
        super().__init__(f"Too many requests, retry after {retry_after} s")
        self.retry_after = retry_after


@dataclass(frozen=True)
class Unit:
    """A unit (UserClusterRelation) the account belongs to."""

    id: int
    name: str


@dataclass(frozen=True)
class Alarm:
    """An alarm of a unit."""

    id: int
    title: str = ""
    text: str = ""
    address: str = ""
    date: datetime | None = None
    priority: bool = False
    closed: bool = False
    lat: float | None = None
    lng: float | None = None
    vehicles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Vehicle:
    """A vehicle of a unit."""

    id: int
    name: str
    fms_status: int | None = None
    note: str = ""
    status_time: datetime | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass(frozen=True)
class UserStatus:
    """A status the user can choose in a unit."""

    id: int
    name: str


@dataclass(frozen=True)
class UnitData:
    """Parsed result of pull/all for one unit."""

    alarm: Alarm | None
    vehicles: dict[int, Vehicle]
    user_status_id: int | None
    user_statuses: list[UserStatus]

    @classmethod
    def from_pull_all(cls, data: dict[str, Any]) -> UnitData:
        """Parse the data object of a pull/all response."""
        return cls(
            alarm=parse_latest_alarm(data),
            vehicles={vehicle.id: vehicle for vehicle in parse_vehicles(data)},
            user_status_id=parse_user_status_id(data),
            user_statuses=parse_user_statuses(data),
        )


class DiveraApi:
    """Client for one DIVERA 24/7 account."""

    def __init__(self, session: aiohttp.ClientSession, access_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._access_key = access_key

    async def fetch_jwt(self) -> str:
        """Fetch a short-lived JWT, needed to authenticate the WebSocket session."""
        jwt = _get_str(await self._request("GET", "auth/jwt"), "jwt")
        if not jwt:
            raise DiveraError("No JWT in server response")
        return jwt

    async def pull_all(self, ucr_id: int | None = None) -> dict[str, Any]:
        """Fetch all data of a unit, or of the default unit if ucr_id is None."""
        return await self._request("GET", "pull/all", ucr_id)

    async def set_user_status(self, ucr_id: int, status_id: int) -> None:
        """Set the user's own status in a unit."""
        await self._request(
            "POST",
            "statusgeber/set-status",
            ucr_id,
            json={"Status": {"id": status_id}},
            expect_data=False,
        )

    async def _request(
        self,
        method: str,
        path: str,
        ucr_id: int | None = None,
        *,
        json: dict[str, Any] | None = None,
        expect_data: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"accesskey": self._access_key}
        if ucr_id is not None:
            params["ucr"] = str(ucr_id)
        try:
            async with self._session.request(
                method, BASE_URL + path, params=params, json=json, timeout=TIMEOUT
            ) as response:
                if response.status == 429:
                    raise DiveraRateLimitError(
                        parse_retry_after(response.headers.get("Retry-After"))
                    )
                if response.status in (401, 403):
                    raise DiveraAuthError(
                        f"Access key rejected (HTTP {response.status})"
                    )
                if response.status != 200:
                    raise DiveraError(
                        f"Request to {path} failed with HTTP {response.status}"
                    )
                if not expect_data:
                    return {}
                root = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise DiveraError(f"Request to {path} failed: {err}") from err
        except ValueError as err:
            raise DiveraError(f"Invalid response of {path}") from err
        data = root.get("data") if isinstance(root, dict) else None
        if not isinstance(data, dict):
            raise DiveraError(f"Response of {path} contains no data")
        return data


def parse_retry_after(value: str | None) -> int:
    """Parse a Retry-After header given in seconds; anything else falls back to the default."""
    try:
        seconds = int(value.strip()) if value else 0
    except ValueError:
        seconds = 0
    return min(seconds, MAX_RETRY_AFTER) if seconds > 0 else DEFAULT_RETRY_AFTER


def parse_user_name(data: dict[str, Any]) -> str:
    """Extract the user's display name from a pull/all response."""
    user = _get_obj(data, "user")
    full_name = f"{_get_str(user, 'firstname')} {_get_str(user, 'lastname')}".strip()
    return (
        full_name
        or _get_str(user, "fullname")
        or _get_str(user, "username")
        or _get_str(user, "email")
    )


def parse_account_id(data: dict[str, Any], units: list[Unit]) -> str:
    """Extract a stable unique id for the user account."""
    if user_id := _get_int(_get_obj(data, "user"), "id"):
        return str(user_id)
    return str(min(unit.id for unit in units))


def parse_units(data: dict[str, Any]) -> list[Unit]:
    """Extract the units (UserClusterRelations) from a pull/all response."""
    units: list[Unit] = []
    ucrs = data.get("ucr")
    if isinstance(ucrs, dict):
        # Keyed by UCR id, the entries themselves may not repeat the id
        for key, value in ucrs.items():
            _add_unit(units, value, _parse_id(key))
    else:
        for value in _values(ucrs):
            _add_unit(units, value, None)
    if not units and (default_id := _get_int(data, "ucr_default")) and default_id > 0:
        units.append(Unit(default_id, _get_str(_get_obj(data, "cluster"), "name")))
    return units


def _add_unit(units: list[Unit], element: Any, fallback_id: int | None) -> None:
    if not isinstance(element, dict):
        return
    unit_id = _get_int(element, "id")
    if unit_id is None:
        unit_id = fallback_id
    if unit_id is not None and unit_id > 0:
        name = _get_str(element, "name") or _get_str(element, "shortname")
        units.append(Unit(unit_id, name))


def parse_latest_alarm(data: dict[str, Any]) -> Alarm | None:
    """Extract the newest alarm (highest id) from a pull/all response."""
    latest: dict[str, Any] | None = None
    latest_id = -1
    for element in _values(_get_obj(data, "alarm").get("items")):
        if isinstance(element, dict):
            alarm_id = _get_int(element, "id")
            if alarm_id is not None and alarm_id > latest_id:
                latest, latest_id = element, alarm_id
    if latest is None:
        return None

    vehicle_names = _get_obj(_get_obj(data, "cluster"), "vehicle")
    vehicles: list[str] = []
    for vehicle in _values(latest.get("vehicle")):
        if isinstance(vehicle, (str, int)) and not isinstance(vehicle, bool):
            vehicle_id = str(vehicle)
            vehicles.append(
                _get_str(_get_obj(vehicle_names, vehicle_id), "name") or vehicle_id
            )

    return Alarm(
        id=latest_id,
        title=_get_str(latest, "title"),
        text=_get_str(latest, "text"),
        address=_get_str(latest, "address"),
        date=_get_datetime(latest, "date"),
        priority=_get_bool(latest, "priority"),
        closed=_get_bool(latest, "closed"),
        lat=_get_float(latest, "lat"),
        lng=_get_float(latest, "lng"),
        vehicles=vehicles,
    )


def parse_vehicles(data: dict[str, Any]) -> list[Vehicle]:
    """Extract the vehicles of the unit from a pull/all response."""
    vehicles: list[Vehicle] = []
    for key, vehicle in _get_obj(_get_obj(data, "cluster"), "vehicle").items():
        if not isinstance(vehicle, dict):
            continue
        vehicle_id = _get_int(vehicle, "id")
        if vehicle_id is None:
            vehicle_id = _parse_id(key)
        if vehicle_id is None:
            continue
        fms_status = _get_int(vehicle, "fmsstatus")
        status_id = _get_int(vehicle, "fmsstatus_id")
        if fms_status is None and status_id is not None and 1 <= status_id <= 10:
            # Status ids 1 to 9 match the FMS status, id 10 is FMS status 0
            fms_status = status_id % 10
        vehicles.append(
            Vehicle(
                id=vehicle_id,
                name=_get_str(vehicle, "name") or _get_str(vehicle, "shortname"),
                fms_status=fms_status,
                note=_get_str(vehicle, "fmsstatus_note"),
                status_time=_get_datetime(vehicle, "fmsstatus_ts"),
                lat=_get_float(vehicle, "lat"),
                lng=_get_float(vehicle, "lng"),
            )
        )
    return vehicles


def parse_user_status_id(data: dict[str, Any]) -> int | None:
    """Extract the id of the user's current status from a pull/all response."""
    return _get_int(_get_obj(data, "status"), "status_id")


def parse_user_statuses(data: dict[str, Any]) -> list[UserStatus]:
    """Extract the statuses a user can choose from, in the unit's sort order."""
    cluster = _get_obj(data, "cluster")
    statuses: dict[int, UserStatus] = {}
    raw = cluster.get("status")
    if isinstance(raw, dict):
        for key, value in raw.items():
            _add_user_status(statuses, value, _parse_id(key))
    else:
        for value in _values(raw):
            _add_user_status(statuses, value, None)

    result: list[UserStatus] = []
    for sorted_id in _values(cluster.get("statussorting")):
        status_id = _parse_id(str(sorted_id))
        if status_id is not None and (status := statuses.pop(status_id, None)):
            result.append(status)
    result.extend(statuses.values())
    return result


def _add_user_status(
    statuses: dict[int, UserStatus], element: Any, fallback_id: int | None
) -> None:
    if not isinstance(element, dict):
        return
    status_id = _get_int(element, "id")
    if status_id is None:
        status_id = fallback_id
    if status_id is not None:
        statuses[status_id] = UserStatus(
            status_id, _get_str(element, "name") or str(status_id)
        )


def _values(element: Any) -> Iterable[Any]:
    """The API serializes collections either as JSON array or, keyed by id, as JSON object."""
    if isinstance(element, list):
        return element
    if isinstance(element, dict):
        return element.values()
    return ()


def _parse_id(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _get_obj(obj: dict[str, Any], member: str) -> dict[str, Any]:
    value = obj.get(member)
    return value if isinstance(value, dict) else {}


def _get_str(obj: dict[str, Any], member: str) -> str:
    value = obj.get(member)
    if value is None or isinstance(value, (dict, list)):
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _get_bool(obj: dict[str, Any], member: str) -> bool:
    # Only a real JSON true counts, like Gson's getAsBoolean in the openHAB binding
    value = obj.get(member)
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _get_int(obj: dict[str, Any], member: str) -> int | None:
    value = obj.get(member)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _get_float(obj: dict[str, Any], member: str) -> float | None:
    value = obj.get(member)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _get_datetime(obj: dict[str, Any], member: str) -> datetime | None:
    seconds = _get_int(obj, member)
    if not seconds:
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None
