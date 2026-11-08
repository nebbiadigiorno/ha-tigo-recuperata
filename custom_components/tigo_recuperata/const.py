"""Constants for Tigo Energia Recuperata."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "tigo_recuperata"
NAME: Final = "Tigo Energia Recuperata"

CONF_SYSTEM_ID: Final = "system_id"
CONF_SYSTEM_NAME: Final = "system_name"
# Token persisted in the config entry, so restarts do not log in again.
CONF_TOKEN: Final = "token"
CONF_TOKEN_EXPIRES: Final = "token_expires"
CONF_API: Final = "api"  # "v4" or "v3": which login worked

# Polling interval in hours, chosen in the options (1-24). The value is the
# reclaimed energy of the current calendar day, reset by Tigo at midnight.
CONF_SCAN_INTERVAL_HOURS: Final = "scan_interval_hours"
DEFAULT_SCAN_INTERVAL_HOURS: Final = 1
MIN_SCAN_INTERVAL_HOURS: Final = 1
MAX_SCAN_INTERVAL_HOURS: Final = 24


def update_interval(hours: int | float | None) -> timedelta:
    """Return the polling interval, clamped to 1-24 h."""
    try:
        value = int(hours) if hours is not None else DEFAULT_SCAN_INTERVAL_HOURS
    except (TypeError, ValueError):
        value = DEFAULT_SCAN_INTERVAL_HOURS
    value = max(MIN_SCAN_INTERVAL_HOURS, min(MAX_SCAN_INTERVAL_HOURS, value))
    return timedelta(hours=value)

# Same login used by the Tigo app (and by the existing 'tigo' integration in
# cloud mode); the v3 Premium API login is the fallback.
V4_HOST: Final = "https://mapi.tigoenergy.com"
V4_LOGIN_URL: Final = f"{V4_HOST}/api/v3/user/login?type=8"
V4_SYSTEMS_URL: Final = f"{V4_HOST}/api/v3/systems/query?limit=100&page=1&sort=-id"
V3_HOST: Final = "https://api2.tigoenergy.com"
V3_LOGIN_URL: Final = f"{V3_HOST}/api/v3/users/login"
V3_SYSTEMS_URL: Final = f"{V3_HOST}/api/v3/systems"

# Endpoint used by the Tigo EI portal for the "Energia recuperata" tile.
# Tried on these hosts in order; the first that accepts the token is kept.
DATA_PATH: Final = "/api/v4/fleet/system/overview/data-lifetime"
DATA_HOSTS: Final = (V4_HOST, "https://ei.tigoenergy.com", V3_HOST)

REQUEST_TIMEOUT: Final = 30
# Log in again this long before the stated token expiry.
EXPIRY_MARGIN: Final = timedelta(days=1)
