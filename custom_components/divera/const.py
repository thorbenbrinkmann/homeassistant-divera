"""Constants for the DIVERA 24/7 integration."""

from typing import Final

DOMAIN: Final = "divera"

CONF_ACCESS_KEY: Final = "access_key"

# Fallback polling in seconds; new data is normally pushed over the WebSocket
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 10

# The server drops idle WebSocket sessions after about 30 seconds
WS_HEARTBEAT: Final = 25
WS_RECONNECT_MIN: Final = 10
WS_RECONNECT_MAX: Final = 300
WS_REFRESH_EVENTS: Final = frozenset({"cluster-pull", "cluster-vehicle", "user-status"})

EVENT_NEW_ALARM: Final = "new_alarm"
EVENT_ALARM_CLOSED: Final = "alarm_closed"
