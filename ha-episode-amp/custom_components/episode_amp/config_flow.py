#     ╭──────────────────────────────────────────────────────╮
#     │                                                      │
#     │          __                                          │
#     │        <(o )___           ✦ EVEREST SMART HOMES ✦    │
#     │         ( ._> /           quack-powered code         │
#     │          `---'            handcrafted by Patrick     │
#     │      __       __       __                            │
#     │    <(o )__  <(o )__  <(o )__    (the interns)        │
#     │     (._>/    (._>/    (._>/                          │
#     │  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~  │
#     │                                                      │
#     │   file     : config_flow.py                          │
#     │   project  : Episode Response Amp – HA integration   │
#     │   author   : Patrick · Everest Smart Homes LLC       │
#     │   created  : 2026-10-20                              │
#     │   license  : MIT (Muscovy Integrity Treaty)          │
#     │   status   : no ducks were harmed, all were fed      │
#     │                                                      │
#     ╰──────────────────────────────────────────────────────╯
"""Config flow for Episode Response Amp."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    EpisodeAmpAuthError,
    EpisodeAmpClient,
    EpisodeAmpConnectionError,
    EpisodeAmpDefaultPasswordError,
    EpisodeAmpError,
    EpisodeAmpLockedOutError,
)
from .const import (
    CONF_MODEL,
    CONF_POLL_INTERVAL,
    CONF_VOLUME_SCALE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DEFAULT_VOLUME_SCALE,
    DOMAIN,
    MODELS,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_MODEL, default="8D"): SelectSelector(
            SelectSelectorConfig(
                options=list(MODELS),
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)


async def _validate(data: dict[str, Any]) -> str:
    """Try to connect + log in. Returns the amp's name on success."""
    client = EpisodeAmpClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        num_outputs=MODELS[data[CONF_MODEL]] // 2,
    )
    try:
        await client.connect()
        await client.refresh_all()
        return client.state.amp_name or data[CONF_HOST]
    finally:
        await client.disconnect()


class EpisodeAmpConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()
            try:
                name = await _validate(user_input)
            except EpisodeAmpDefaultPasswordError:
                errors["base"] = "default_password"
            except EpisodeAmpLockedOutError:
                errors["base"] = "locked_out"
            except EpisodeAmpAuthError:
                errors["base"] = "invalid_auth"
            except EpisodeAmpConnectionError:
                errors["base"] = "cannot_connect"
            except EpisodeAmpError:
                _LOGGER.exception("Unexpected error validating amp")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Episode {user_input[CONF_MODEL]} – {name}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            merged = {**entry.data, **user_input}
            try:
                await _validate(merged)
            except EpisodeAmpDefaultPasswordError:
                errors["base"] = "default_password"
            except EpisodeAmpLockedOutError:
                errors["base"] = "locked_out"
            except EpisodeAmpAuthError:
                errors["base"] = "invalid_auth"
            except EpisodeAmpConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EpisodeAmpOptionsFlow()


class EpisodeAmpOptionsFlow(OptionsFlow):
    """Volume scale + poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VOLUME_SCALE,
                    default=opts.get(CONF_VOLUME_SCALE, DEFAULT_VOLUME_SCALE),
                ): NumberSelector(
                    NumberSelectorConfig(min=10, max=255, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(min=10, max=300, step=5, mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
