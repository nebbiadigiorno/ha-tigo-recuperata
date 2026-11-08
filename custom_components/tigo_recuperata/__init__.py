"""Tigo Energia Recuperata: today's energy reclaimed by the TS4 optimizers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TigoClient
from .const import CONF_API, CONF_TOKEN, CONF_TOKEN_EXPIRES
from .coordinator import TigoReclaimedCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type TigoConfigEntry = ConfigEntry[TigoReclaimedCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TigoConfigEntry) -> bool:
    """Set up from a config entry."""
    client = TigoClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        token=entry.data.get(CONF_TOKEN),
        expires=entry.data.get(CONF_TOKEN_EXPIRES),
        api=entry.data.get(CONF_API),
    )
    coordinator = TigoReclaimedCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TigoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
