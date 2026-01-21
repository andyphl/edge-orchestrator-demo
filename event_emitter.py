from collections import defaultdict
from typing import Callable, Any, Dict, List, Optional


class EventEmitter:
    def __init__(self):
        self._listeners: Dict[str,
                              List[Callable[[Optional[Any]], None]]] = defaultdict(list)

    def on(self, event: str, handler: Callable[[Optional[Any]], None]):
        self._listeners[event].append(handler)

    def emit(self, event: str, data: Any = None):
        print(f"[emit] {event} -> {data}")
        for handler in self._listeners.get(event, []):
            handler(data)
