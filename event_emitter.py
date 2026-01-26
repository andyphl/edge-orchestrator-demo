import os
from collections import defaultdict, deque
from threading import Lock
from typing import Callable, Any, Dict, List, Optional


class EventEmitter:
    def __init__(self):
        self._listeners: Dict[str,
                              List[Callable[[Optional[Any]], None]]] = defaultdict(list)
        # Avoid per-event stdout overhead (important for high-FPS pipelines).
        # Enable by setting EVENT_EMITTER_DEBUG=1.
        self._debug: bool = os.getenv("EVENT_EMITTER_DEBUG", "0") == "1"
        # Prevent recursive emit() causing recursion errors by dispatching via a queue.
        self._queue: "deque[tuple[str, Any]]" = deque()
        self._is_emitting: bool = False
        self._lock = Lock()

    def on(self, event: str, handler: Callable[[Optional[Any]], None]):
        self._listeners[event].append(handler)

    def emit(self, event: str, data: Any = None):
        # Queue the event; if we're already dispatching, return and let the
        # outer dispatcher loop pick it up (avoids recursion).
        with self._lock:
            self._queue.append((event, data))
            if self._is_emitting:
                return
            self._is_emitting = True

        try:
            while True:
                with self._lock:
                    if not self._queue:
                        self._is_emitting = False
                        return
                    evt, payload = self._queue.popleft()

                if self._debug:
                    print(f"[emit] {evt} -> {payload}")

                # Snapshot listeners to avoid issues if handlers register more handlers.
                listeners = list(self._listeners.get(evt, []))
                for handler in listeners:
                    handler(payload)
        finally:
            # Ensure state resets even if a handler raises.
            with self._lock:
                self._is_emitting = False
