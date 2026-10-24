"""Runtime object: talks to the phone and holds the call state."""
from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .call import PhoneState
from .const import CALL_LOG_SIZE, DOMAIN, EVENT_CALL, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class YealinkError(Exception):
    """Phone didn't accept the command."""


class YealinkPhone:
    def __init__(self, hass: HomeAssistant, entry_id: str, host: str, username: str, password: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.host = host
        self._auth = aiohttp.BasicAuth(username, password)
        self.state = PhoneState(log_size=CALL_LOG_SIZE)
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._listeners: list[Callable[[], None]] = []
        self.phonebook = None  # PhonebookCoordinator, set when a phonebook URL is configured
        self.selected_contact: str | None = None

    async def async_load(self) -> None:
        self.state.load(await self._store.async_load())

    # ---- phone -> HA ----------------------------------------------------
    @callback
    def handle_event(self, event: str, remote: str | None, name: str | None) -> None:
        self.state.apply(event, remote, name, dt_util.now())
        self.hass.bus.async_fire(
            EVENT_CALL,
            {
                "config_entry_id": self.entry_id,
                "event": event,
                "number": self.state.last_number if event in ("incoming", "missed") else None,
                "caller": self.state.last_caller if event in ("incoming", "missed") else None,
                "state": self.state.state,
            },
        )
        self._store.async_delay_save(self.state.to_store, 5)
        for listener in self._listeners:
            listener()

    @callback
    def reset_missed(self) -> None:
        self.state.missed = 0
        self._store.async_delay_save(self.state.to_store, 5)
        for listener in self._listeners:
            listener()

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    # ---- HA -> phone (Action URI) ---------------------------------------
    async def _send(self, key: str) -> None:
        url = f"http://{self.host}/servlet?key={key}"
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, auth=self._auth, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 401:
                    raise YealinkError("authentication failed")
                if resp.status == 403:
                    raise YealinkError("forbidden, add Home Assistant's IP to the phone's Action URI allow list")
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise YealinkError(f"cannot reach phone at {self.host}: {err}") from err

    async def async_dial(self, number: str) -> None:
        # '+' would turn into a space without encoding
        await self._send("number=" + quote(number.replace(" ", ""), safe=""))

    async def async_hangup(self) -> None:
        await self._send("CALLEND")

    async def async_test(self) -> None:
        """Harmless request to check host + credentials during setup."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(f"http://{self.host}/", auth=self._auth,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 401:
                    raise YealinkError("authentication failed")
        except aiohttp.ClientError as err:
            raise YealinkError(f"cannot reach phone at {self.host}: {err}") from err
