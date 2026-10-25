"""Yealink SIP phone integration: call events via Action URL, dial/hangup via Action URI."""
from __future__ import annotations

import logging

import voluptuous as vol
from aiohttp import web
from homeassistant.components import persistent_notification, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_NAME,
    ATTR_NUMBER,
    CONF_PHONEBOOK_URL,
    CONF_WEBHOOK_ID,
    DOMAIN,
    PHONE_EVENTS,
    SERVICE_DIAL,
    SERVICE_DIAL_CONTACT,
    SERVICE_HANGUP,
    SERVICE_RESET_MISSED,
)
from .card import async_setup_card
from .phone import YealinkError, YealinkPhone
from .phonebook import PhonebookCoordinator, PhonebookError, find_contact
from .notify import async_call_notification
from .provision import action_urls, ha_base_url, provisioning_file

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SELECT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type YealinkConfigEntry = ConfigEntry[YealinkPhone]


def _phone_for(hass: HomeAssistant, call: ServiceCall) -> YealinkPhone:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    wanted = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if len(entries) != 1:
        raise ServiceValidationError(
            "No phone found" if not entries else "Several phones configured, pass config_entry_id"
        )
    return entries[0].runtime_data


class YealinkProvisionView(HomeAssistantView):
    """Serves the auto-provisioning file. The phone can't do HA auth, the webhook id in the path is the secret."""

    url = "/api/yealink_provision/{token}/{filename}"
    name = "api:yealink_provision"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, token: str, filename: str) -> web.Response:
        if not filename.endswith(".cfg"):
            return web.Response(status=404)
        for entry in self.hass.config_entries.async_loaded_entries(DOMAIN):
            if entry.data.get(CONF_WEBHOOK_ID) == token:
                _LOGGER.debug("Phone %s fetched provisioning file %s", request.remote, filename)
                body = provisioning_file(ha_base_url(self.hass, entry), entry)
                return web.Response(text=body, content_type="text/plain")
        return web.Response(status=404)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Services + provisioning view are registered once, they pick the phone at call time."""
    if getattr(hass, "http", None) is not None:
        hass.http.register_view(YealinkProvisionView(hass))
    await async_setup_card(hass)

    async def dial(call: ServiceCall) -> None:
        try:
            await _phone_for(hass, call).async_dial(call.data[ATTR_NUMBER])
        except YealinkError as err:
            raise HomeAssistantError(str(err)) from err

    async def hangup(call: ServiceCall) -> None:
        try:
            await _phone_for(hass, call).async_hangup()
        except YealinkError as err:
            raise HomeAssistantError(str(err)) from err

    async def reset_missed(call: ServiceCall) -> None:
        _phone_for(hass, call).reset_missed()

    async def dial_contact(call: ServiceCall) -> None:
        phone = _phone_for(hass, call)
        if phone.phonebook is None or not phone.phonebook.data:
            raise ServiceValidationError("No phonebook configured or not loaded yet (integration options)")
        try:
            contact = find_contact(phone.phonebook.data, call.data[ATTR_NAME])
        except PhonebookError as err:
            raise ServiceValidationError(str(err)) from err
        try:
            await phone.async_dial(contact.number)
        except YealinkError as err:
            raise HomeAssistantError(str(err)) from err

    entry_schema = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
    hass.services.async_register(
        DOMAIN, SERVICE_DIAL, dial, schema=vol.Schema({vol.Required(ATTR_NUMBER): cv.string, **entry_schema})
    )
    hass.services.async_register(DOMAIN, SERVICE_HANGUP, hangup, schema=vol.Schema(entry_schema))
    hass.services.async_register(DOMAIN, SERVICE_RESET_MISSED, reset_missed, schema=vol.Schema(entry_schema))
    hass.services.async_register(
        DOMAIN, SERVICE_DIAL_CONTACT, dial_contact,
        schema=vol.Schema({vol.Required(ATTR_NAME): cv.string, **entry_schema}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: YealinkConfigEntry) -> bool:
    phone = YealinkPhone(
        hass, entry.entry_id, entry.data[CONF_HOST], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    await phone.async_load()
    entry.runtime_data = phone

    if url := entry.options.get(CONF_PHONEBOOK_URL):
        phone.phonebook = PhonebookCoordinator(hass, url, entry)
        # don't block setup if the phonebook is down, it retries every 15 min
        await phone.phonebook.async_refresh()
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    async def handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
        event = request.query.get("event", "")
        _LOGGER.debug("Webhook hit from %s: %s", request.remote, dict(request.query))
        if event not in PHONE_EVENTS:
            _LOGGER.warning("Ignoring unknown phone event %r from %s (query: %s)",
                            event, request.remote, dict(request.query))
            return web.Response(status=400)
        phone.handle_event(event, request.query.get("from"), request.query.get("name"))
        hass.async_create_task(
            async_call_notification(hass, dict(entry.options), event, phone.state.last_caller)
        )
        return web.Response(status=200)

    webhook_id = entry.data[CONF_WEBHOOK_ID]
    webhook.async_register(
        hass, DOMAIN, f"Yealink {entry.title}", webhook_id, handle_webhook,
        allowed_methods={"GET", "POST"}, local_only=True,
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))
    _LOGGER.debug("Listening for phone events on /api/webhook/%s", webhook_id)

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Yealink",
        name=f"Yealink {phone.base.split('://')[-1]}",
    )
    phone.device_id = device.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _notify_action_urls(hass, entry)
    return True


async def _async_reload(hass: HomeAssistant, entry: YealinkConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: YealinkConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _notify_action_urls(hass: HomeAssistant, entry: YealinkConfigEntry) -> None:
    """Show how to point the phone at HA. Shown again whenever the detected HA address changes."""
    base = ha_base_url(hass, entry)
    if entry.data.get("_urls_shown_for") == base:
        return
    token = entry.data[CONF_WEBHOOK_ID]
    provision = f"{base}/api/yealink_provision/{token}/"
    manual = "\n".join(f"- {k}: `{v}`" for k, v in action_urls(base, token).items())
    persistent_notification.async_create(
        hass,
        "**Automatic (recommended):** on the phone go to **Settings → Auto Provision**, set\n\n"
        f"Server URL: `{provision}`\n\n"
        "then press **Autoprovision Now**. The phone sets all Action URLs and allows Home Assistant "
        "to dial on its own.\n\n"
        f"Detected Home Assistant address: `{base}`. Wrong? Set it in the integration options.\n\n"
        f"<details><summary>Manual setup instead</summary>\n\nFeatures → Action URL:\n{manual}\n\n"
        f"Features → Remote Control → Action URI allow IP list: `{base.split('://')[-1].split(':')[0]}`\n</details>",
        title=f"Yealink setup: {entry.title}",
        notification_id=f"{DOMAIN}_{entry.entry_id}_urls",
    )
    hass.config_entries.async_update_entry(entry, data={**entry.data, "_urls_shown_for": base})
