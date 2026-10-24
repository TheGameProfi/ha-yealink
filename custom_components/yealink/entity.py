"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .phone import YealinkPhone


class YealinkEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, phone: YealinkPhone, key: str) -> None:
        self.phone = phone
        self._attr_unique_id = f"{phone.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, phone.entry_id)},
            name=f"Yealink {phone.base.split('://')[-1]}",
            manufacturer="Yealink",
            configuration_url=phone.base,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.phone.add_listener(self.async_write_ha_state))
