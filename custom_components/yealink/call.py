"""Pure call state logic, no Home Assistant imports so it's easy to test."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

STATE_IDLE = "idle"
STATE_RINGING = "ringing"
STATE_DIALING = "dialing"
STATE_ACTIVE = "active"
STATES = [STATE_IDLE, STATE_RINGING, STATE_DIALING, STATE_ACTIVE]


def clean_number(remote: str | None) -> str:
    """'sip:0761123@tel.t-online.de' -> '0761123'."""
    if not remote:
        return ""
    m = re.match(r"^(?:sips?:)?([^@;]+)", remote.strip())
    return m.group(1) if m else remote.strip()


def resolve_name(name: str | None, number: str) -> str:
    """Phone sends the number as display name when it doesn't know the caller."""
    name = (name or "").strip()
    if not name or name == number or clean_number(name) == number:
        return number or "Unknown"
    return name


@dataclass
class PhoneState:
    state: str = STATE_IDLE
    last_caller: str | None = None
    last_number: str | None = None
    missed: int = 0
    log: list[dict] = field(default_factory=list)
    log_size: int = 50
    _current: dict | None = None

    def apply(self, event: str, remote: str | None, name: str | None, now: datetime) -> None:
        number = clean_number(remote)
        caller = resolve_name(name, number)

        if event == "incoming":
            self.state = STATE_RINGING
            self.last_caller, self.last_number = caller, number
            self._current = {"start": now.isoformat(), "direction": "in", "number": number, "name": caller}

        elif event == "outgoing":
            self.state = STATE_DIALING
            self._current = {"start": now.isoformat(), "direction": "out", "number": number, "name": caller}

        elif event == "established":
            self.state = STATE_ACTIVE
            if self._current is not None:
                self._current["answered"] = now.isoformat()

        elif event == "missed":
            self.state = STATE_IDLE
            self.missed += 1
            call = self._current or {"start": now.isoformat(), "direction": "in", "number": number, "name": caller}
            self._finish(call, "missed", now)

        elif event == "ended":
            self.state = STATE_IDLE
            if self._current is not None:
                call = self._current
                if call["direction"] == "out":
                    result = "outgoing" if "answered" in call else "not_reached"
                else:
                    result = "answered" if "answered" in call else "missed"
                    if result == "missed":
                        self.missed += 1
                self._finish(call, result, now)

    def _finish(self, call: dict, result: str, now: datetime) -> None:
        call = {**call, "end": now.isoformat(), "result": result}
        self.log.insert(0, call)
        del self.log[self.log_size:]
        self._current = None

    def to_store(self) -> dict:
        return {"log": self.log, "missed": self.missed,
                "last_caller": self.last_caller, "last_number": self.last_number}

    def load(self, data: dict | None) -> None:
        if not data:
            return
        self.log = data.get("log", [])[: self.log_size]
        self.missed = data.get("missed", 0)
        self.last_caller = data.get("last_caller")
        self.last_number = data.get("last_number")
