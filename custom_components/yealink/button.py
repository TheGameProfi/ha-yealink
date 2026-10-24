"""Dial the contact picked in the select."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import YealinkConfigEntry
from .entity import YealinkEntity
from .phone import YealinkError


async def async_setup_entry(hass: HomeAssistant, entry: YealinkConfigEntry, add: AddEntitiesCallback) -> None:
    phone = entry.runtime_data
    entities = [HangupButton(phone, "hangup")]
    if phone.phonebook is not None:
        entities.append(DialSelectedButton(phone, "dial_selected"))
    add(entities)


class DialSelectedButton(YealinkEntity, ButtonEntity):
    _attr_icon = "mdi:phone-outgoing"

    async def async_press(self) -> None:
        label = self.phone.selected_contact
        contact = next((c for c in self.phone.phonebook.data or [] if c.label == label), None)
        if contact is None:
            raise ServiceValidationError("Pick a contact first")
        try:
            await self.phone.async_dial(contact.number)
        except YealinkError as err:
            raise HomeAssistantError(str(err)) from err


class HangupButton(YealinkEntity, ButtonEntity):
    _attr_icon = "mdi:phone-hangup"

    async def async_press(self) -> None:
        try:
            await self.phone.async_hangup()
        except YealinkError as err:
            raise HomeAssistantError(str(err)) from err
