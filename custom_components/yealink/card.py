"""Contacts dashboard card: serves the JS, loads it on every dashboard, hands it the contacts over websocket."""
from __future__ import annotations

import re
from pathlib import Path

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration

from .const import DOMAIN

CARD_FILE = "yealink-contacts-card.js"
CARD_URL = f"/{DOMAIN}_static/{CARD_FILE}"

# 'Anna Müller (Mobil)' as written by the CardDAV converter -> ('Anna Müller', 'Mobil')
_KIND = re.compile(r"^(.*\S) \(([^()]+)\)$")


def split_kind(name: str) -> tuple[str, str]:
    m = _KIND.match(name)
    return (m[1], m[2]) if m else (name, "")


async def async_setup_card(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_contacts)
    if getattr(hass, "http", None) is None:
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend" / CARD_FILE), False)]
    )
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url

        version = (await async_get_integration(hass, DOMAIN)).version
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")  # version busts the browser cache on update


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/contacts"})
@callback
def ws_contacts(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    phones = []
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        pb = entry.runtime_data.phonebook
        contacts = []
        for c in (pb.data or []) if pb else []:
            person, kind = split_kind(c.name)
            contacts.append({"name": person, "kind": kind, "number": c.number})
        phones.append({"entry_id": entry.entry_id, "title": entry.title, "phonebook": pb is not None,
                       "contacts": contacts})
    connection.send_result(msg["id"], {"phones": phones})
