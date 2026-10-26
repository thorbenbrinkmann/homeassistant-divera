"""Config flow for the DIVERA 24/7 integration."""

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
from homeassistant.const import CONF_SCAN_INTERVAL, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    DiveraApi,
    DiveraAuthError,
    DiveraError,
    parse_account_id,
    parse_units,
    parse_user_name,
)
from .const import (
    CONF_ACCESS_KEY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_SCAN_INTERVAL,
        step=1,
        unit_of_measurement=UnitOfTime.SECONDS,
        mode=NumberSelectorMode.BOX,
    )
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): SCAN_INTERVAL_SELECTOR,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): SCAN_INTERVAL_SELECTOR,
    }
)


class DiveraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a DIVERA 24/7 account by its personal access key."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DiveraOptionsFlow:
        """Return the options flow handler."""
        return DiveraOptionsFlow()

    async def _validate(
        self, access_key: str
    ) -> tuple[dict[str, str], str | None, str | None]:
        """Check the key; return errors, a stable account id and the user's name."""
        api = DiveraApi(async_get_clientsession(self.hass), access_key)
        try:
            data = await api.pull_all()
        except DiveraAuthError:
            return {"base": "invalid_auth"}, None, None
        except DiveraError:
            _LOGGER.debug("Cannot connect to DIVERA 24/7", exc_info=True)
            return {"base": "cannot_connect"}, None, None
        units = parse_units(data)
        if not units:
            return {"base": "no_units"}, None, None
        account_id = parse_account_id(data, units)
        title = parse_user_name(data) or "DIVERA 24/7"
        return {}, account_id, title

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the access key and polling interval."""
        errors: dict[str, str] = {}
        if user_input is not None:
            access_key = user_input[CONF_ACCESS_KEY].strip()
            errors, account_id, title = await self._validate(access_key)
            if not errors:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title or "DIVERA 24/7",
                    data={CONF_ACCESS_KEY: access_key},
                    options={
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    },
                )
        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the access key was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new access key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            access_key = user_input[CONF_ACCESS_KEY].strip()
            errors, _, _ = await self._validate(access_key)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_ACCESS_KEY: access_key}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )


class DiveraOptionsFlow(OptionsFlowWithReload):
    """Configure options for DIVERA 24/7."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the polling interval."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
