"""Config flow: host + phone web UI credentials."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .const import CONF_HA_URL, CONF_PHONEBOOK_URL, CONF_WEBHOOK_ID, DOMAIN
from .phone import YealinkError, YealinkPhone
from .phonebook import PhonebookError, fetch_phonebook

_LOGGER = logging.getLogger(__name__)

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
        placeholders = {"error": ""}
        if user_input is not None:
            # "192.168.1.50" -> auto (http, then https). "https://..." or "http://..." -> forced
            entered = user_input[CONF_HOST].strip().rstrip("/")
            bare = entered.removeprefix("http://").removeprefix("https://")
            await self.async_set_unique_id(bare)
            self._abort_if_unique_id_configured()

            phone = YealinkPhone(self.hass, "test", entered, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            try:
                base = await phone.async_test()
            except YealinkError as err:
                _LOGGER.warning("Yealink connection test failed: %s", err)
                errors["base"] = "invalid_auth" if "authentication" in str(err) else "cannot_connect"
                placeholders["error"] = str(err)
            else:
                return self.async_create_entry(
                    title=f"Yealink {bare}",
                    data={**user_input, CONF_HOST: base, CONF_WEBHOOK_ID: webhook.async_generate_id()},
                )

        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors,
                                    description_placeholders=placeholders)


class YealinkOptionsFlow(OptionsFlow):
    """Optional phonebook URL for dialing contacts by name."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = (user_input.get(CONF_PHONEBOOK_URL) or "").strip()
            ha_url = (user_input.get(CONF_HA_URL) or "").strip().rstrip("/")
            if url:
                try:
                    contacts = await fetch_phonebook(self.hass, url)
                except PhonebookError as err:
                    errors["base"] = "invalid_phonebook" if "XML" in str(err) or "root" in str(err) else "cannot_fetch"
                else:
                    if not contacts:
                        errors["base"] = "empty_phonebook"
            if ha_url and not ha_url.startswith(("http://", "https://")):
                errors[CONF_HA_URL] = "invalid_url"
            if not errors:
                data = {}
                if url:
                    data[CONF_PHONEBOOK_URL] = url
                if ha_url:
                    data[CONF_HA_URL] = ha_url
                return self.async_create_entry(data=data)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(CONF_PHONEBOOK_URL, description={"suggested_value": opts.get(CONF_PHONEBOOK_URL, "")}): str,
                vol.Optional(CONF_HA_URL, description={"suggested_value": opts.get(CONF_HA_URL, "")}): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
