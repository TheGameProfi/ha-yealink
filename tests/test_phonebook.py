"""Phonebook: parsing, lookup, options flow, select + button + dial_contact."""
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yealink.const import CONF_PHONEBOOK_URL, CONF_WEBHOOK_ID, DOMAIN
from custom_components.yealink.phonebook import PhonebookError, find_contact, parse_phonebook

PB_URL = "http://192.168.3.20/phonebook/tok.xml"
XML = """<?xml version="1.0" encoding="UTF-8"?><YealinkIPPhoneDirectory>
<DirectoryEntry><Name>Mama</Name><Telephone>+491701234567</Telephone><Telephone>01701234567</Telephone></DirectoryEntry>
<DirectoryEntry><Name>Mama</Name><Telephone>+49761123456</Telephone></DirectoryEntry>
<DirectoryEntry><Name>Martin Oberle</Name><Telephone>+4917055</Telephone></DirectoryEntry>
<DirectoryEntry><Name>Martin Weber</Name><Telephone>+4917066</Telephone></DirectoryEntry>
<DirectoryEntry><Name>Björn &amp; Co</Name><Telephone>+4917077</Telephone></DirectoryEntry>
</YealinkIPPhoneDirectory>"""
DATA = {"host": "192.168.1.50", "username": "admin", "password": "pw", CONF_WEBHOOK_ID: "hook123"}


def test_parse_and_find():
    c = parse_phonebook(XML)
    assert [x.label for x in c] == ["Björn & Co", "Mama", "Mama (2)", "Martin Oberle", "Martin Weber"]
    assert find_contact(c, "mama").number == "+491701234567"
    assert find_contact(c, "Mama (2)").number == "+49761123456"
    assert find_contact(c, "oberle").name == "Martin Oberle"
    with pytest.raises(PhonebookError, match="ambiguous"):
        find_contact(c, "martin")
    with pytest.raises(PhonebookError, match="no contact"):
        find_contact(c, "zorro")
    with pytest.raises(PhonebookError):
        parse_phonebook("<html>nope</html>")


async def _setup(hass, aioclient_mock):
    await async_setup_component(hass, "http", {})
    aioclient_mock.get(PB_URL, text=XML)
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options={CONF_PHONEBOOK_URL: PB_URL},
                            title="Yealink", unique_id="192.168.1.50")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass, domain, suffix):
    return next(s for s in hass.states.async_all(domain) if s.entity_id.endswith(suffix))


async def test_select_button_and_service(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock)
    sel = _entity(hass, "select", "contact")
    assert "Mama (2)" in sel.attributes["options"]

    await hass.services.async_call("select", "select_option",
                                   {"entity_id": sel.entity_id, "option": "Mama (2)"}, blocking=True)
    assert _entity(hass, "select", "contact").attributes["number"] == "+49761123456"

    aioclient_mock.get("http://192.168.1.50/servlet?key=number=%2B49761123456", status=200)
    btn = _entity(hass, "button", "call_contact")
    await hass.services.async_call("button", "press", {"entity_id": btn.entity_id}, blocking=True)

    aioclient_mock.get("http://192.168.1.50/servlet?key=number=%2B4917055", status=200)
    await hass.services.async_call(DOMAIN, "dial_contact", {"name": "oberle"}, blocking=True)
    urls = [str(c[1]) for c in aioclient_mock.mock_calls]
    assert any("%2B49761123456" in u for u in urls) and any("%2B4917055" in u for u in urls)

    with pytest.raises(ServiceValidationError, match="ambiguous"):
        await hass.services.async_call(DOMAIN, "dial_contact", {"name": "martin"}, blocking=True)


async def test_no_phonebook_no_entities(hass: HomeAssistant) -> None:
    await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, title="Yealink", unique_id="x")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.states.async_all("select")
    assert [s.entity_id for s in hass.states.async_all("button")][0].endswith("hang_up")
    with pytest.raises(ServiceValidationError, match="No phonebook"):
        await hass.services.async_call(DOMAIN, "dial_contact", {"name": "mama"}, blocking=True)


async def test_options_flow(hass: HomeAssistant, aioclient_mock) -> None:
    await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, title="Yealink", unique_id="y")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    aioclient_mock.get("http://bad/pb.xml", text="<html/>")
    aioclient_mock.get(PB_URL, text=XML)

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {CONF_PHONEBOOK_URL: "http://bad/pb.xml"})
    assert flow["errors"] == {"base": "invalid_phonebook"}
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {CONF_PHONEBOOK_URL: PB_URL})
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done()
    # reloaded with phonebook -> select exists now
    assert _entity(hass, "select", "contact")
