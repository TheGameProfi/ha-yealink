"""Ringing binary sensor, the thing you actually automate on."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import YealinkConfigEntry
from .call import STATE_RINGING
from .entity import YealinkEntity


async def async_setup_entry(hass: HomeAssistant, entry: YealinkConfigEntry, add: AddEntitiesCallback) -> None:
    add([RingingSensor(entry.runtime_data, "ringing")])


class RingingSensor(YealinkEntity, BinarySensorEntity):
    _attr_icon = "mdi:phone-ring"

    @property
    def is_on(self) -> bool:
        return self.phone.state.state == STATE_RINGING
