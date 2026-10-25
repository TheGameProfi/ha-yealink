"""IP detection, provisioning file, setup notification, device triggers."""
from unittest.mock import patch

from homeassistant.components import automation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
import pytest
from homeassistant.components.device_automation import DeviceAutomationType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_get_device_automations

from custom_components.yealink.const import CONF_HA_URL, CONF_WEBHOOK_ID, DOMAIN
from custom_components.yealink.provision import local_ip_towards

DATA = {"host": "http://192.168.2.171", "username": "admin", "password": "pw", CONF_WEBHOOK_ID: "hook123"}


async def _setup(hass, options=None):
    await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=options or {}, title="Yealink 192.168.2.171",
                            unique_id="192.168.2.171")
    entry.add_to_hass(hass)
    with patch("custom_components.yealink.provision.local_ip_towards", return_value="192.168.2.30"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.mark.real_ip
def test_local_ip_towards_returns_an_ip(socket_enabled):
    from custom_components.yealink import provision
    ip = provision.local_ip_towards("127.0.0.1")
    assert ip and ip.count(".") == 3


async def test_notification_uses_detected_ip(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    notes = [s for s in hass.states.async_all("persistent_notification")]
    from homeassistant.components.persistent_notification import _async_get_or_create_notifications
    msg = next(iter(_async_get_or_create_notifications(hass).values()))["message"]
    assert "192.168.2.30:8123/api/yealink_provision/hook123/" in msg
    assert "192.168.2.85" not in msg
    assert entry.data["_urls_shown_for"].startswith("http://192.168.2.30")


async def test_provisioning_file(hass: HomeAssistant, hass_client_no_auth) -> None:
    await _setup(hass)
    client = await hass_client_no_auth()
    with patch("custom_components.yealink.provision.local_ip_towards", return_value="192.168.2.30"):
        r = await client.get("/api/yealink_provision/hook123/y000000000000.cfg")
        body = await r.text()
        assert r.status == 200
        assert body.startswith("#!version:1.0.0.1")
        assert "action_url.missed_call = http://192.168.2.30:8123/api/webhook/hook123?event=missed&from=$remote" in body
        assert "features.action_uri_limit_ip = 192.168.2.30" in body
        assert (await client.get("/api/yealink_provision/WRONG/y000000000000.cfg")).status == 404
        assert (await client.get("/api/yealink_provision/hook123/passwd")).status == 404


async def test_ha_url_override(hass: HomeAssistant, hass_client_no_auth) -> None:
    await _setup(hass, {CONF_HA_URL: "http://10.0.0.5:8123/"})
    client = await hass_client_no_auth()
    with patch("custom_components.yealink.provision.local_ip_towards", return_value="192.168.2.30"):
        body = await (await client.get("/api/yealink_provision/hook123/x.cfg")).text()
    assert "http://10.0.0.5:8123/api/webhook/hook123" in body
    # the phone checks where requests come from (route), not the URL it calls back
    assert "features.action_uri_limit_ip = 192.168.2.30,10.0.0.5" in body


async def test_device_triggers(hass: HomeAssistant, hass_client_no_auth) -> None:
    entry = await _setup(hass)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, device.id)
    assert {t["type"] for t in triggers if t["domain"] == DOMAIN} == {"incoming", "outgoing", "established", "ended", "missed"}

    calls = []
    hass.services.async_register("test", "record", lambda call: calls.append(call.data))
    assert await async_setup_component(hass, automation.DOMAIN, {automation.DOMAIN: [{
        "triggers": [{"platform": "device", "domain": DOMAIN, "device_id": device.id, "type": "missed"}],
        "actions": [{"action": "test.record", "data": {"who": "{{ trigger.event.data.caller }}"}}],
    }]})
    client = await hass_client_no_auth()
    await client.get("/api/webhook/hook123", params={"event": "incoming", "from": "sip:0761@x", "name": "Mama"})
    await client.get("/api/webhook/hook123", params={"event": "missed", "from": "sip:0761@x", "name": "Mama"})
    await hass.async_block_till_done()
    assert calls == [{"who": "Mama"}]
