"""Call state, last caller, missed calls."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import YealinkConfigEntry
from .call import STATES
from .entity import YealinkEntity


async def async_setup_entry(hass: HomeAssistant, entry: YealinkConfigEntry, add: AddEntitiesCallback) -> None:
    phone = entry.runtime_data
    add([CallStateSensor(phone, "call_state"), LastCallerSensor(phone, "last_caller"),
         MissedCallsSensor(phone, "missed_calls")])


class CallStateSensor(YealinkEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES

    @property
    def native_value(self) -> str:
        return self.phone.state.state


class LastCallerSensor(YealinkEntity, SensorEntity):
    _attr_icon = "mdi:account-voice"
    # call log is handy in the UI but would bloat the recorder DB
    _unrecorded_attributes = frozenset({"call_log"})

    @property
    def native_value(self) -> str | None:
        return self.phone.state.last_caller

    @property
    def extra_state_attributes(self) -> dict:
        return {"number": self.phone.state.last_number, "call_log": self.phone.state.log}


class MissedCallsSensor(YealinkEntity, SensorEntity):
    _attr_icon = "mdi:phone-missed"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        return self.phone.state.missed
