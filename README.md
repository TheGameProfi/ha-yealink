# Yealink Phone for Home Assistant

Call events from a Yealink SIP phone (via Action URL) and dialing/hangup (via Action URI). Local push, no polling, no cloud.

## Entities

| Entity | What |
|---|---|
| `binary_sensor.*_ringing` | on while the phone rings |
| `sensor.*_call_state` | `idle` / `ringing` / `dialing` / `active` |
| `sensor.*_last_caller` | name (or number), attributes: `number`, `call_log` (last 50 calls, not recorded) |
| `sensor.*_missed_calls` | counter, reset with `yealink.reset_missed` |
| `button.*_hang_up` | ends the current call |
| `select.*_contact` | contact picker *(only with phonebook)* |
| `button.*_call_contact` | dials the picked contact *(only with phonebook)* |

Event `yealink_call` is fired on every phone event (`event`, `caller`, `number`, `state`).

## Services

- `yealink.dial` with `number`
- `yealink.hangup`
- `yealink.reset_missed`
- `yealink.dial_contact` with `name` (exact name, or a unique part of it: `oberle` works, `martin` with two Martins errors)

## Phonebook (optional)

Integration options → Phonebook URL: the same Yealink XML URL the phone uses (e.g. from the CardDAV→XML phonebook service). Refreshes every 15 min. Same name with several numbers shows up as `Mama`, `Mama (2)`, ...

### Contacts card

Ships with the integration, nothing to add under resources. Dashboard → Add card → **Yealink contacts**, or:

```yaml
type: custom:yealink-contacts-card
title: Contacts          # optional
config_entry_id: abc123  # optional, only with several phones
max_height: 420px        # optional, list scrolls beyond this
```

Search by name (start of any word, accents ignored: `max web` finds *Dr. Max Peter Weber*) or by part of a number. One row per person, a button per number (`Mobil`, `Privat`, ... when the phonebook names them like `Anna Müller (Mobil)`); tap to dial, Enter dials when only one number is left. A bar with a hang-up button shows while a call is ringing or active.

## Install

HACS → Custom repositories → this repo, type Integration. Or copy `custom_components/yealink` into your HA config folder. Restart, then Settings → Devices & Services → Add → Yealink.

## Phone setup

After adding the integration, a notification shows a provisioning URL. On the phone:

1. **Settings → Auto Provision → Server URL**: paste that URL
2. press **Autoprovision Now**

The phone pulls a config file from Home Assistant that sets all Action URLs and allows Home Assistant to dial. No copying of webhook IDs.

Home Assistant's address is detected from the network route to the phone, not from HA's network settings. If it's still wrong (e.g. reverse proxy, odd Docker networking), set **Home Assistant URL** in the integration options. The notification pops up again whenever the detected address changes.

Manual setup is in the notification too, if you'd rather not use provisioning.

## Notifications

Integration options → set a notify service (e.g. `notify.mobile_app_pixel`) and tick **Notify while ringing** and/or **Notify on missed call**. No automation needed.

With the companion app, the "ringing" notification is replaced by "missed call", or removed when you pick up, so they don't pile up.

## Automations

Device triggers are built in: automation editor → **Device** → your Yealink → *Incoming call*, *Missed call*, *Call answered*, *Call ended*, *Outgoing call*. `trigger.event.data.caller` and `.number` hold who called.

## Example

```yaml
alias: Notify on missed call
trigger:
  - platform: event
    event_type: yealink_call
    event_data: { event: missed }
action:
  - service: notify.notify
    data:
      title: Missed call
      message: "{{ trigger.event.data.caller }}"
```

## Dev

```bash
uv venv -p 3.13 && uv pip install pytest-homeassistant-custom-component
.venv/bin/pytest
```
