"""Config flow: host + phone web UI credentials."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .const import CONF_PHONEBOOK_URL, CONF_WEBHOOK_ID, DOMAIN
from .phone import YealinkError, YealinkPhone
from .phonebook import PhonebookError, fetch_phonebook

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class YealinkConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> YealinkOptionsFlow:
        return YealinkOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip().removeprefix("http://").rstrip("/")
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            phone = YealinkPhone(self.hass, "test", host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            try:
                await phone.async_test()
            except YealinkError as err:
                errors["base"] = "invalid_auth" if "authentication" in str(err) else "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Yealink {host}",
                    data={**user_input, CONF_HOST: host, CONF_WEBHOOK_ID: webhook.async_generate_id()},
                )

        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)


class YealinkOptionsFlow(OptionsFlow):
    """Optional phonebook URL for dialing contacts by name."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = (user_input.get(CONF_PHONEBOOK_URL) or "").strip()
            if url:
                try:
                    contacts = await fetch_phonebook(self.hass, url)
                except PhonebookError as err:
                    errors["base"] = "invalid_phonebook" if "XML" in str(err) or "root" in str(err) else "cannot_fetch"
                else:
                    if not contacts:
                        errors["base"] = "empty_phonebook"
            if not errors:
                return self.async_create_entry(data={CONF_PHONEBOOK_URL: url} if url else {})

        current = self.config_entry.options.get(CONF_PHONEBOOK_URL, "")
        schema = vol.Schema({vol.Optional(CONF_PHONEBOOK_URL, description={"suggested_value": current}): str})
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
