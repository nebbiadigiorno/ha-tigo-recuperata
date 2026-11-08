"""Config flow: Premium API credentials, then the system to read."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TigoAuthError, TigoClient, TigoEndpointUnauthorized, TigoError
from .const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SYSTEM_ID,
    CONF_SYSTEM_NAME,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


class TigoReclaimedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TigoReclaimedOptionsFlow:
        """Return the options flow."""
        return TigoReclaimedOptionsFlow()

    def __init__(self) -> None:
        """Initialize."""
        self._credentials: dict[str, Any] = {}
        self._systems: list[dict[str, Any]] = []
        self._client: TigoClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Premium API username and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = TigoClient(
                async_get_clientsession(self.hass),
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.async_login()
                systems = await client.async_get_systems()
            except TigoAuthError:
                errors["base"] = "invalid_auth"
            except TigoError:
                _LOGGER.exception("Tigo login/systems failed")
                errors["base"] = "cannot_connect"
            else:
                if not systems:
                    errors["base"] = "no_systems"
                else:
                    self._credentials = user_input
                    self._systems = systems
                    self._client = client
                    if len(systems) == 1:
                        return await self._async_finish(systems[0])
                    return await self.async_step_system()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, {CONF_USERNAME: (user_input or {}).get(CONF_USERNAME)}
            ),
            errors=errors,
        )

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the system when the account has more than one."""
        if user_input is not None:
            sid = int(user_input[CONF_SYSTEM_ID])
            system = next(s for s in self._systems if s["id"] == sid)
            return await self._async_finish(system)
        options = [
            selector.SelectOptionDict(value=str(s["id"]), label=f"{s['name']} ({s['id']})")
            for s in self._systems
        ]
        return self.async_show_form(
            step_id="system",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SYSTEM_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def _async_finish(self, system: dict[str, Any]) -> ConfigFlowResult:
        """Check that the reclaimed endpoint answers, then create the entry."""
        await self.async_set_unique_id(str(system["id"]))
        self._abort_if_unique_id_configured()
        assert self._client is not None
        try:
            await self._client.async_get_reclaimed_today(system["id"])
        except TigoEndpointUnauthorized:
            return self.async_abort(reason="endpoint_unauthorized")
        except TigoError:
            _LOGGER.exception("Tigo reclaimed endpoint failed")
            return self.async_abort(reason="cannot_read")
        return self.async_create_entry(
            title=f"Tigo {system['name']} - energia recuperata",
            data={
                **self._credentials,
                CONF_SYSTEM_ID: system["id"],
                CONF_SYSTEM_NAME: system["name"],
                **self._client.token_state(),
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Credentials stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            client = TigoClient(
                async_get_clientsession(self.hass),
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.async_login()
            except TigoAuthError:
                errors["base"] = "invalid_auth"
            except TigoError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={**user_input, **client.token_state()}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, {CONF_USERNAME: entry.data.get(CONF_USERNAME)}
            ),
            errors=errors,
        )


class TigoReclaimedOptionsFlow(OptionsFlowWithReload):
    """Choose how often the Tigo cloud is called (1-24 hours)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_HOURS: int(user_input[CONF_SCAN_INTERVAL_HOURS])
                }
            )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_HOURS, default=current
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_HOURS,
                        max=MAX_SCAN_INTERVAL_HOURS,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                        unit_of_measurement="h",
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
