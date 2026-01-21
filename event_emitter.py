from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional


class EventEmitter:
    def __init__(self):
        self._listeners: Dict[str,
                              List[Callable[[Optional[Any]], None]]] = defaultdict(list)

    def on(self, event: str, handler: Callable[[Optional[Any]], None]):
        self._listeners[event].append(handler)

    def emit(self, event: str, data: Any = None):
        listeners = self._listeners.get(event, [])
        print(
            f"[EventEmitter] emit({event}, data={data}), listeners count: {len(listeners)}")
        if len(listeners) == 0:
            print(
                f"[EventEmitter] WARNING: No listeners registered for event '{event}'")
        for i, handler in enumerate(listeners):
            print(f"[EventEmitter] Calling handler {i} for event '{event}'")
            try:
                handler(data)
                print(
                    f"[EventEmitter] Handler {i} for event '{event}' completed successfully")
            except Exception as e:
                print(
                    f"[EventEmitter] Handler {i} for event '{event}' raised exception: {e}")
                import traceback
                traceback.print_exc()
