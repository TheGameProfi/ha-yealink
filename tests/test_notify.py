"""Built-in call notifications."""
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yealink.const import (
    CONF_NOTIFY_INCOMING, CONF_NOTIFY_MISSED, CONF_NOTIFY_SERVICE, CONF_WEBHOOK_ID, DOMAIN,
)

DATA = {"host": "http://192.168.2.171", "username": "admin", "password": "pw", CONF_WEBHOOK_ID: "hook123"}


async def _setup(hass, options):
    await async_setup_component(hass, "http", {})
    sent = []
    hass.services.async_register("notify", "mobile_app_pixel", lambda c: sent.append(dict(c.data)))
    hass.services.async_register("notify", "telegram", lambda c: sent.append(dict(c.data)))
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=options, title="Y", unique_id="y")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return sent


async def _events(hass, client, *events):
    for ev in events:
        await client.get("/api/webhook/hook123", params={"event": ev, "from": "sip:0761@x", "name": "Mama"})
        await hass.async_block_till_done()


OPTS = {CONF_NOTIFY_SERVICE: "notify.mobile_app_pixel", CONF_NOTIFY_INCOMING: True, CONF_NOTIFY_MISSED: True}


async def test_missed_call_replaces_ringing(hass: HomeAssistant, hass_client_no_auth) -> None:
    sent = await _setup(hass, OPTS)
    await _events(hass, await hass_client_no_auth(), "incoming", "missed", "ended")
    assert [s.get("title") for s in sent] == ["📞 Incoming call", "Missed call"]
    assert all(s["data"]["tag"] == "yealink_call" for s in sent)
    assert sent[1]["message"] == "Mama"


async def test_answered_clears_ringing(hass: HomeAssistant, hass_client_no_auth) -> None:
    sent = await _setup(hass, OPTS)
    await _events(hass, await hass_client_no_auth(), "incoming", "established", "ended")
    assert [s["message"] for s in sent] == ["Mama", "clear_notification"]


async def test_only_missed(hass: HomeAssistant, hass_client_no_auth) -> None:
    sent = await _setup(hass, {**OPTS, CONF_NOTIFY_INCOMING: False})
    await _events(hass, await hass_client_no_auth(), "incoming", "missed", "ended")
    assert [s["title"] for s in sent] == ["Missed call"]


async def test_non_companion_service_gets_no_tags(hass: HomeAssistant, hass_client_no_auth) -> None:
    sent = await _setup(hass, {**OPTS, CONF_NOTIFY_SERVICE: "notify.telegram"})
    await _events(hass, await hass_client_no_auth(), "incoming", "established", "ended")
    assert sent == [{"title": "📞 Incoming call", "message": "Mama"}]  # no clear_notification spam


async def test_off_by_default(hass: HomeAssistant, hass_client_no_auth) -> None:
    sent = await _setup(hass, {})
    await _events(hass, await hass_client_no_auth(), "incoming", "missed")
    assert sent == []


async def test_options_flow_validates_service(hass: HomeAssistant) -> None:
    await _setup(hass, {})
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {CONF_NOTIFY_SERVICE: "notify.nope"})
    assert flow["errors"] == {CONF_NOTIFY_SERVICE: "unknown_notify"}
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {CONF_NOTIFY_SERVICE: "mobile_app_pixel", CONF_NOTIFY_MISSED: True})
    assert flow["type"] == "create_entry"
    assert flow["data"][CONF_NOTIFY_SERVICE] == "notify.mobile_app_pixel"


async def test_notify_entity(hass: HomeAssistant, hass_client_no_auth) -> None:
    """notify.mbg14_phone style entity -> notify.send_message, no tags."""
    await async_setup_component(hass, "http", {})
    sent = []
    hass.services.async_register("notify", "send_message", lambda c: sent.append(dict(c.data)))
    hass.states.async_set("notify.mbg14_phone", "unknown")
    opts = {CONF_NOTIFY_SERVICE: "notify.mbg14_phone", CONF_NOTIFY_INCOMING: True, CONF_NOTIFY_MISSED: True}
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=opts, title="Y", unique_id="y")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _events(hass, await hass_client_no_auth(), "incoming", "missed", "ended")
    assert [s["title"] for s in sent] == ["📞 Incoming call", "Missed call"]
    assert all(s["entity_id"] == "notify.mbg14_phone" and "data" not in s for s in sent)

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {CONF_NOTIFY_SERVICE: "notify.mbg14_phone", CONF_NOTIFY_MISSED: True})
    assert flow["type"] == "create_entry"
