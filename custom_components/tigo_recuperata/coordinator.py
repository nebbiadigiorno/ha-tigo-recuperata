"""Hourly coordinator for today's reclaimed energy."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TigoAuthError, TigoClient, TigoError
from .const import CONF_SCAN_INTERVAL_HOURS, CONF_SYSTEM_ID, DOMAIN, update_interval

_LOGGER = logging.getLogger(__name__)


class TigoReclaimedCoordinator(DataUpdateCoordinator[float]):
    """Fetch today's reclaimed energy (Wh) every 1-24 hours (options)."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: TigoClient
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval(
                entry.options.get(CONF_SCAN_INTERVAL_HOURS)
            ),
        )
        self.client = client
        self.system_id = int(entry.data[CONF_SYSTEM_ID])

    async def _async_update_data(self) -> float:
        try:
            value = await self.client.async_get_reclaimed_today(self.system_id)
        except TigoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TigoError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self._persist_token()
        return value

    def _persist_token(self) -> None:
        """Save a new token in the entry so a restart does not log in again."""
        state = self.client.token_state()
        entry = self.config_entry
        if all(entry.data.get(k) == v for k, v in state.items()):
            return
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, **state}
        )
