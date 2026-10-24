"""Contacts from the Yealink XML phonebook (the one the phone already uses)."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class PhonebookError(Exception):
    """Phonebook couldn't be fetched or parsed."""


@dataclass(frozen=True)
class Contact:
    label: str          # unique, shown in the select
    name: str
    number: str         # first <Telephone>, used for dialing
    numbers: tuple[str, ...]


def parse_phonebook(xml_text: str) -> list[Contact]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as err:
        raise PhonebookError(f"not valid XML: {err}") from err
    if not root.tag.endswith("IPPhoneDirectory"):
        raise PhonebookError(f"unexpected root element <{root.tag}>")

    raw: list[tuple[str, tuple[str, ...]]] = []
    for entry in root.iter("DirectoryEntry"):
        name = (entry.findtext("Name") or "").strip()
        nums = tuple(n.text.strip() for n in entry.findall("Telephone") if n.text and n.text.strip())
        if name and nums:
            raw.append((name, nums))

    # same name with several numbers -> "Mama", "Mama (2)", ...
    seen: dict[str, int] = {}
    contacts = []
    for name, nums in sorted(raw, key=lambda x: x[0].lower()):
        seen[name] = seen.get(name, 0) + 1
        label = name if seen[name] == 1 else f"{name} ({seen[name]})"
        contacts.append(Contact(label=label, name=name, number=nums[0], numbers=nums))
    return contacts


async def fetch_phonebook(hass: HomeAssistant, url: str) -> list[Contact]:
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            resp.raise_for_status()
            text = await resp.text()
    except aiohttp.ClientError as err:
        raise PhonebookError(f"cannot fetch phonebook: {err}") from err
    return parse_phonebook(text)


def find_contact(contacts: list[Contact], query: str) -> Contact:
    """Exact label/name match first, then a unique substring match."""
    q = query.strip().lower()
    for c in contacts:
        if c.label.lower() == q:
            return c
    exact = [c for c in contacts if c.name.lower() == q]
    if exact:
        return exact[0]
    partial = [c for c in contacts if q in c.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise PhonebookError(f"no contact matching '{query}'")
    names = ", ".join(c.label for c in partial[:8])
    raise PhonebookError(f"'{query}' is ambiguous: {names}")


class PhonebookCoordinator(DataUpdateCoordinator[list[Contact]]):
    def __init__(self, hass: HomeAssistant, url: str, entry) -> None:
        super().__init__(hass, _LOGGER, name="Yealink phonebook", update_interval=timedelta(minutes=15),
                         config_entry=entry)
        self.url = url

    async def _async_update_data(self) -> list[Contact]:
        try:
            return await fetch_phonebook(self.hass, self.url)
        except PhonebookError as err:
            raise UpdateFailed(str(err)) from err
