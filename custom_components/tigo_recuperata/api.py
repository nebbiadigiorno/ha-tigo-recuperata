"""Minimal Tigo cloud client: login + today's reclaimed energy only.

Independent of the 'tigo' custom integration: own session state, own token,
no shared module or hass.data key.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

import aiohttp

from .const import (
    DATA_HOSTS,
    DATA_PATH,
    EXPIRY_MARGIN,
    REQUEST_TIMEOUT,
    V3_LOGIN_URL,
    V3_SYSTEMS_URL,
    V4_LOGIN_URL,
    V4_SYSTEMS_URL,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
_NET_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError)


class TigoError(Exception):
    """Generic communication error."""


class TigoAuthError(TigoError):
    """Wrong credentials (login refused)."""


class TigoEndpointUnauthorized(TigoError):
    """Login works, but the reclaimed-energy endpoint refuses the token."""


def _parse_expires(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class TigoClient:
    """Talk to the Tigo cloud with the account credentials."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        token: str | None = None,
        expires: str | None = None,
        api: str | None = None,
    ) -> None:
        """Initialize, optionally reusing a persisted token."""
        self._session = session
        self._username = username
        self._password = password
        self.token = token
        self.expires = _parse_expires(expires)
        self.api = api  # "v4" | "v3" | None
        self._data_host: str | None = None

    # ------------------------------------------------------------------ auth
    def token_state(self) -> dict[str, Any]:
        """Return what to persist in the config entry."""
        return {
            "token": self.token,
            "token_expires": self.expires.isoformat() if self.expires else None,
            "api": self.api,
        }

    def _expired(self) -> bool:
        if self.expires is None:
            return False
        now = datetime.now(self.expires.tzinfo or timezone.utc)
        return now >= self.expires - EXPIRY_MARGIN

    async def _login_v4(self) -> None:
        async with self._session.post(
            V4_LOGIN_URL,
            json={"username": self._username, "password": self._password},
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status in (401, 403):
                raise TigoAuthError(f"v4 login refused (HTTP {resp.status})")
            if resp.status != 200:
                raise TigoError(f"v4 login error HTTP {resp.status}")
            data = await resp.json(content_type=None)
        user = data.get("user") if isinstance(data, dict) else None
        if not isinstance(user, dict) or not user.get("auth"):
            raise TigoError("v4 login response has no token")
        self.token = user["auth"]
        self.expires = _parse_expires(user.get("expires"))
        self.api = "v4"

    async def _login_v3(self) -> None:
        async with self._session.get(
            V3_LOGIN_URL,
            auth=aiohttp.BasicAuth(self._username, self._password),
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status in (401, 403):
                raise TigoAuthError(f"v3 login refused (HTTP {resp.status})")
            if resp.status != 200:
                raise TigoError(f"v3 login error HTTP {resp.status}")
            data = await resp.json(content_type=None)
        try:
            self.token = data["user"]["auth"]
        except (KeyError, TypeError) as err:
            raise TigoError("v3 login response has no token") from err
        self.expires = None
        self.api = "v3"

    async def async_login(self) -> None:
        """Log in: v4 (app login) first, v3 Premium API as fallback.

        Wrong credentials on v4 are final (no second attempt on v3).
        """
        try:
            await self._login_v4()
            return
        except TigoAuthError:
            raise
        except (TigoError, *_NET_ERRORS) as err:
            _LOGGER.info("v4 login failed (%s), trying v3", err)
        try:
            await self._login_v3()
        except TigoError:
            raise
        except _NET_ERRORS as err:
            raise TigoError(f"Login failed: {err}") from err

    # -------------------------------------------------------------- requests
    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if self.token is None or self._expired():
            await self.async_login()
        for attempt in (1, 2):
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/json",
                    },
                    timeout=_TIMEOUT,
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        await self.async_login()  # token rejected: once
                        continue
                    if resp.status in (401, 403):
                        raise TigoEndpointUnauthorized(f"HTTP {resp.status} from {url}")
                    if resp.status != 200:
                        raise TigoError(f"HTTP {resp.status} from {url}")
                    return await resp.json(content_type=None)
            except TigoError:
                raise
            except _NET_ERRORS as err:
                raise TigoError(f"Request to {url} failed: {err}") from err
        raise TigoEndpointUnauthorized(f"HTTP 401 from {url}")

    async def async_get_systems(self) -> list[dict[str, Any]]:
        """Return [{'id': int, 'name': str}] for the account."""
        url = V4_SYSTEMS_URL if self.api == "v4" else V3_SYSTEMS_URL
        payload = await self._get(url)
        if isinstance(payload, dict):
            rows = payload.get("systems") or payload.get("data") or []
        else:
            rows = payload or []
        systems: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = row.get("system_id", row.get("id"))
            if sid is None:
                continue
            systems.append({"id": int(sid), "name": str(row.get("name") or sid)})
        return systems

    async def async_get_reclaimed_today(self, system_id: int) -> float:
        """Return the reclaimed energy of the current calendar day, in Wh."""
        params = {"sysid": system_id, "range": "day"}
        hosts = [self._data_host] if self._data_host else list(DATA_HOSTS)
        last_err: TigoError | None = None
        for host in hosts:
            try:
                payload = await self._get(f"{host}{DATA_PATH}", params)
            except (TigoEndpointUnauthorized, TigoError) as err:
                if isinstance(err, TigoAuthError):
                    raise
                _LOGGER.debug("Reclaimed endpoint failed on %s: %s", host, err)
                last_err = err
                continue
            if not isinstance(payload, dict) or payload.get("reclaimed") is None:
                last_err = TigoError(f"Unexpected response from {host}: {payload!r:.200}")
                continue
            if self._data_host != host:
                _LOGGER.info("Reclaimed energy read from %s", host)
                self._data_host = host
            return float(payload["reclaimed"])
        self._data_host = None
        raise last_err or TigoEndpointUnauthorized("No host accepted the token")
