"""Constants for the Yealink integration."""

DOMAIN = "yealink"

CONF_WEBHOOK_ID = "webhook_id"

EVENT_CALL = "yealink_call"

SERVICE_DIAL = "dial"
SERVICE_HANGUP = "hangup"
SERVICE_RESET_MISSED = "reset_missed"

ATTR_NUMBER = "number"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

STORAGE_VERSION = 1
CALL_LOG_SIZE = 50

# events the phone sends via Action URL (?event=...)
PHONE_EVENTS = ("incoming", "outgoing", "established", "ended", "missed")

CONF_PHONEBOOK_URL = "phonebook_url"
SERVICE_DIAL_CONTACT = "dial_contact"
ATTR_NAME = "name"
