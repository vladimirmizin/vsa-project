from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Protocol

from vsa_commerce.tracking.events import Event

log = logging.getLogger(__name__)


class EventLog(Protocol):
    def append(self, event: Event) -> None: ...

    def read(self) -> list[Event]: ...


class InMemoryEventLog:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def append(self, event: Event) -> None:
        self._events.append(event)

    def read(self) -> list[Event]:
        return list(self._events)


class JsonlEventLog:
    """One JSON event per line. In production: an events table or a queue to the warehouse."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def append(self, event: Event) -> None:
        line = event.model_dump_json() + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    def read(self) -> list[Event]:
        if not self.path.is_file():
            return []
        events = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                events.append(Event.model_validate_json(line))
            except ValueError:
                log.warning("%s:%d: skipping unreadable event", self.path, number)
        return events
