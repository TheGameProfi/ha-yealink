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

## Install

HACS → Custom repositories → this repo, type Integration. Or copy `custom_components/yealink` into your HA config folder. Restart, then Settings → Devices & Services → Add → Yealink.

## Phone setup

After adding the integration, a notification shows the exact Action URLs. Paste them into the phone under **Features → Action URL**, and add Home Assistant's IP to **Features → Remote Control → Action URI allow IP list**.

If the notification shows a hostname the phone can't resolve (like `homeassistant.local`), replace it with the IP.

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
