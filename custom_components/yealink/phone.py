"""Runtime object: talks to the phone and holds the call state."""
from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
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
        # host may be "192.168.1.50" or "https://192.168.1.50"
        self.base = host if host.startswith(("http://", "https://")) else f"http://{host}"
        self._auth = aiohttp.BasicAuth(username, password)
        self.state = PhoneState(log_size=CALL_LOG_SIZE)
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._listeners: list[Callable[[], None]] = []
        self._session: aiohttp.ClientSession | None = None
        self.phonebook = None  # PhonebookCoordinator, set when a phonebook URL is configured
        self.selected_contact: str | None = None

    async def async_load(self) -> None:
        self.state.load(await self._store.async_load())

    # ---- phone -> HA ----------------------------------------------------
    @callback
    def handle_event(self, event: str, remote: str | None, name: str | None) -> None:
        self.state.apply(event, remote, name, dt_util.now())
        _LOGGER.debug("Event %s -> state %s, last caller %s", event, self.state.state, self.state.last_caller)
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
    def _http(self) -> aiohttp.ClientSession:
        """Own session: Yealink web servers send huge security headers that the default
        8 KB header limit rejects, and their certificates are always self-signed."""
        if self._session is None:
            self._session = async_create_clientsession(
                self.hass, verify_ssl=False, max_line_size=65536, max_field_size=65536
            )
        return self._session

    async def _get(self, path: str, base: str | None = None) -> int:
        base = base or self.base
        try:
            # never follow redirects: "/" bounces to the login form, and that's already proof enough
            async with self._http().get(f"{base}{path}", auth=self._auth, allow_redirects=False,
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status
        except TimeoutError as err:
            raise YealinkError(f"timeout talking to {base}") from err
        except aiohttp.ClientError as err:
            raise YealinkError(f"{type(err).__name__} talking to {base}: {err}") from err

    async def _send(self, key: str) -> None:
        status = await self._get(f"/servlet?key={key}")
        _LOGGER.debug("Action URI key=%s -> HTTP %s", key, status)
        if status == 401:
            raise YealinkError("authentication failed")
        if status == 403:
            raise YealinkError("forbidden, add Home Assistant's IP to the phone's Action URI allow list")
        if 300 <= status < 400:
            raise YealinkError("phone redirected to its login page, check username/password and the Action URI allow list")
        if status >= 400:
            raise YealinkError(f"phone answered HTTP {status}")

    async def async_dial(self, number: str) -> None:
        # '+' would turn into a space without encoding
        await self._send("number=" + quote(number.replace(" ", ""), safe=""))

    async def async_hangup(self) -> None:
        await self._send("CALLEND")

    async def async_test(self) -> str:
        """Check reachability + pick the scheme. Without an explicit scheme, try http then https.
        Returns the working base URL."""
        explicit = self.host.startswith(("http://", "https://"))
        candidates = [self.base] if explicit else [f"http://{self.host}", f"https://{self.host}"]
        errors = []
        for base in candidates:
            try:
                status = await self._get("/", base)
            except YealinkError as err:
                errors.append(str(err))
                continue
            if status == 401:
                raise YealinkError("authentication failed")
            self.base = base
            return base
        raise YealinkError(" / ".join(errors))
