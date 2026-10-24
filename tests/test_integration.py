"""End-to-end: config flow, webhook events -> entities, dial service -> phone request."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yealink.const import CONF_WEBHOOK_ID, DOMAIN

ENTRY_DATA = {"host": "192.168.1.50", "username": "admin", "password": "pw", CONF_WEBHOOK_ID: "hook123"}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Yealink 192.168.1.50", unique_id="192.168.1.50")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == "form"
    with patch("custom_components.yealink.config_flow.YealinkPhone.async_test", return_value="http://192.168.1.50"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "http://192.168.1.50/", "username": "admin", "password": "pw"}
        )
    assert result["type"] == "create_entry"
    assert result["data"]["host"] == "http://192.168.1.50"
    assert result["data"][CONF_WEBHOOK_ID]


async def test_call_flow(hass: HomeAssistant, hass_client_no_auth) -> None:
    await _setup(hass)
    client = await hass_client_no_auth()
    events = []
    hass.bus.async_listen("yealink_call", lambda e: events.append(e.data))

    r = await client.get("/api/webhook/hook123", params={"event": "incoming", "from": "sip:07611234@tel.t-online.de", "name": "Mama"})
    assert r.status == 200
    await hass.async_block_till_done()

    ringing = [s for s in hass.states.async_all("binary_sensor") if s.entity_id.endswith("ringing")][0]
    assert ringing.state == "on"
    last = [s for s in hass.states.async_all("sensor") if s.entity_id.endswith("last_caller")][0]
    assert last.state == "Mama" and last.attributes["number"] == "07611234"
    assert events[-1]["caller"] == "Mama"

    await client.get("/api/webhook/hook123", params={"event": "missed", "from": "sip:07611234@x", "name": "Mama"})
    await client.get("/api/webhook/hook123", params={"event": "ended"})
    await hass.async_block_till_done()

    missed = [s for s in hass.states.async_all("sensor") if s.entity_id.endswith("missed_calls")][0]
    assert missed.state == "1"
    state = [s for s in hass.states.async_all("sensor") if s.entity_id.endswith("call_state")][0]
    assert state.state == "idle"

    bad = await client.get("/api/webhook/hook123", params={"event": "nonsense"})
    assert bad.status == 400

    await hass.services.async_call(DOMAIN, "reset_missed", {}, blocking=True)
    missed = [s for s in hass.states.async_all("sensor") if s.entity_id.endswith("missed_calls")][0]
    assert missed.state == "0"


async def test_dial(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass)
    aioclient_mock.get("http://192.168.1.50/servlet?key=number=%2B49761123", status=200)
    await hass.services.async_call(DOMAIN, "dial", {"number": "+49 761 123"}, blocking=True)
    assert aioclient_mock.call_count == 1

    aioclient_mock.clear_requests()
    aioclient_mock.get("http://192.168.1.50/servlet?key=CALLEND", status=403)
    import pytest
    from homeassistant.exceptions import HomeAssistantError
    with pytest.raises(HomeAssistantError, match="allow list"):
        await hass.services.async_call(DOMAIN, "hangup", {}, blocking=True)


async def test_config_flow_shows_real_error(hass: HomeAssistant, aioclient_mock) -> None:
    import aiohttp
    aioclient_mock.get("http://192.168.1.60/", exc=aiohttp.ClientConnectionError("No route to host"))
    aioclient_mock.get("https://192.168.1.60/", exc=aiohttp.ClientConnectionError("No route to host"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.60", "username": "admin", "password": "pw"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    assert "No route to host" in result["description_placeholders"]["error"]

    aioclient_mock.clear_requests()
    # different host, the first flow is still open and would abort as already_in_progress
    aioclient_mock.get("http://192.168.1.61/", exc=TimeoutError())
    aioclient_mock.get("https://192.168.1.61/", exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.61", "username": "admin", "password": "pw"}
    )
    assert "timeout" in result["description_placeholders"]["error"]


async def test_https_host(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get("https://192.168.1.70/", status=200)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "https://192.168.1.70/", "username": "admin", "password": "pw"}
    )
    assert result["type"] == "create_entry"
    assert result["data"]["host"] == "https://192.168.1.70"


async def test_config_flow_accepts_login_redirect(hass: HomeAssistant, aioclient_mock) -> None:
    # real T41S answers / with 302 -> login form, that must count as reachable
    aioclient_mock.get("http://192.168.2.171/", status=302,
                       headers={"Location": "/servlet?m=mod_listener&p=login&q=loginForm&jumpto=status"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.2.171", "username": "admin", "password": "pw"}
    )
    assert result["type"] == "create_entry"



async def test_auto_falls_back_to_https(hass: HomeAssistant, aioclient_mock) -> None:
    import aiohttp
    aioclient_mock.get("http://192.168.1.80/", exc=aiohttp.ClientConnectionError("refused"))
    aioclient_mock.get("https://192.168.1.80/", status=302)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.80", "username": "admin", "password": "pw"}
    )
    assert result["type"] == "create_entry"
    assert result["data"]["host"] == "https://192.168.1.80"
    assert result["title"] == "Yealink 192.168.1.80"


async def test_redirect_to_login_counts_as_reachable(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get("http://192.168.1.90/", status=302, headers={"Location": "/servlet?m=mod_listener&p=login"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.90", "username": "admin", "password": "pw"}
    )
    assert result["type"] == "create_entry"
    assert result["data"]["host"] == "http://192.168.1.90"
