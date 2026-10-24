"""Built-in call notifications, configured in the integration options."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import CONF_NOTIFY_INCOMING, CONF_NOTIFY_MISSED, CONF_NOTIFY_SERVICE

_LOGGER = logging.getLogger(__name__)

TAG = "yealink_call"


async def async_call_notification(hass: HomeAssistant, options: dict, event: str, caller: str | None) -> None:
    target = options.get(CONF_NOTIFY_SERVICE)
    if not target or "." not in target:
        return
    domain, service = target.split(".", 1)
    if not hass.services.has_service(domain, service):
        _LOGGER.warning("Notify service %s not found, skipping call notification", target)
        return

    # companion app understands tags: same tag replaces the notification, clear_notification removes it
    companion = service.startswith("mobile_app_")
    extra = {"data": {"tag": TAG}} if companion else {}
    who = caller or "Unknown"

    if event == "incoming" and options.get(CONF_NOTIFY_INCOMING):
        data = {"title": "📞 Incoming call", "message": who, **extra}
    elif event == "missed" and options.get(CONF_NOTIFY_MISSED):
        data = {"title": "Missed call", "message": who, **extra}
    elif event in ("established", "ended") and options.get(CONF_NOTIFY_INCOMING) and companion:
        # picked up or hung up: drop the "ringing" notification (a missed one already replaced it)
        if event == "ended" and options.get(CONF_NOTIFY_MISSED):
            return
        data = {"message": "clear_notification", "data": {"tag": TAG}}
    else:
        return

    try:
        await hass.services.async_call(domain, service, data, blocking=False)
    except Exception as err:  # never let a notification break event handling
        _LOGGER.warning("Sending call notification via %s failed: %s", target, err)
