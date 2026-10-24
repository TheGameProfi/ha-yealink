"""Contact picker, only present when a phonebook URL is configured."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import YealinkConfigEntry
from .entity import YealinkEntity


async def async_setup_entry(hass: HomeAssistant, entry: YealinkConfigEntry, add: AddEntitiesCallback) -> None:
    phone = entry.runtime_data
    if phone.phonebook is not None:
        add([ContactSelect(phone, "contact")])


class ContactSelect(YealinkEntity, SelectEntity):
    _attr_icon = "mdi:card-account-phone"
    # hundreds of names would bloat every recorder row
    _unrecorded_attributes = frozenset({"options"})

    @property
    def available(self) -> bool:
        return bool(self.phone.phonebook.data)

    @property
    def options(self) -> list[str]:
        return [c.label for c in self.phone.phonebook.data or []]

    @property
    def current_option(self) -> str | None:
        sel = self.phone.selected_contact
        return sel if sel in self.options else None

    @property
    def extra_state_attributes(self) -> dict:
        contact = next((c for c in self.phone.phonebook.data or [] if c.label == self.current_option), None)
        return {"number": contact.number if contact else None}

    async def async_select_option(self, option: str) -> None:
        self.phone.selected_contact = option
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.phone.phonebook.async_add_listener(self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()
