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
    domain, name = target.split(".", 1)

    # two flavours: notify entity (notify.send_message, UI shows these) or legacy service (notify.mobile_app_x)
    is_entity = hass.states.get(target) is not None
    if not is_entity and not hass.services.has_service(domain, name):
        _LOGGER.warning("Notify target %s not found, skipping call notification", target)
        return

    # only the legacy companion app service understands tags (replace / clear_notification)
    companion = not is_entity and name.startswith("mobile_app_")
    who = caller or "Unknown"

    if event == "incoming" and options.get(CONF_NOTIFY_INCOMING):
        title, message = "📞 Incoming call", who
    elif event == "missed" and options.get(CONF_NOTIFY_MISSED):
        title, message = "Missed call", who
    elif event in ("established", "ended") and options.get(CONF_NOTIFY_INCOMING) and companion:
        # picked up or hung up: drop the "ringing" notification (a missed one already replaced it)
        if event == "ended" and options.get(CONF_NOTIFY_MISSED):
            return
        title, message = None, "clear_notification"
    else:
        return

    try:
        if is_entity:
            await hass.services.async_call(
                "notify", "send_message", {"entity_id": target, "title": title, "message": message}, blocking=False
            )
        else:
            data = {"message": message}
            if title:
                data["title"] = title
            if companion:
                data["data"] = {"tag": TAG}
            await hass.services.async_call(domain, name, data, blocking=False)
    except Exception as err:  # never let a notification break event handling
        _LOGGER.warning("Sending call notification via %s failed: %s", target, err)
