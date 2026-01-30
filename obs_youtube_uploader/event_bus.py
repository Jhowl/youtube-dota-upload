from __future__ import annotations

from dataclasses import dataclass
import json
import queue
import threading
from typing import Any


@dataclass(frozen=True)
class Event:
    type: str
    data: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "data": self.data}, ensure_ascii=True)


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[Event]] = set()

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        event = Event(type=event_type, data=data)
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                continue

    def subscribe(self) -> queue.Queue[Event]:
        q: queue.Queue[Event] = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[Event]) -> None:
        with self._lock:
            self._subscribers.discard(q)


EVENT_BUS = EventBus()
