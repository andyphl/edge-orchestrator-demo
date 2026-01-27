import queue
from typing import Any, TypedDict


class EventToken(TypedDict):
    id: int


class EventQueueConfig(TypedDict):
    max_size: int


class EventQueue:
    _queue: queue.Queue[Any]

    def __init__(self, cfg: EventQueueConfig):
        self._queue = queue.Queue(maxsize=cfg.get('max_size', 100))

    def put(self, token: Any):
        self._queue.put(token)

    def get(self) -> Any:
        try:
            return self._queue.get()
        except queue.Empty:
            return None

    def empty(self) -> bool:
        return self._queue.empty()

    def size(self) -> int:
        return self._queue.qsize()
