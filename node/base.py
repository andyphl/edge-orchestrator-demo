from queue import PriorityQueue, Queue
from typing import Any, Dict, Protocol, TypedDict

from aiwin_resource.creator import ResourceCreator
from aiwin_resource.instance_manager import ResourceInstanceManager
from event_emitter import EventEmitter
from store.file import BaseStore


class FrameRef(TypedDict):
    """Frame reference - 輕量級的 frame 引用，不包含實際圖像數據"""
    resource_key: str  # Resource 的 key，用於從 resource_manager 獲取實際數據
    timestamp: float  # 時間戳
    seq: int  # 序列號，用於追蹤處理順序


class BaseNodeContext(TypedDict):
    resource_manager: ResourceInstanceManager
    resource_creator: ResourceCreator
    file_store: BaseStore
    event: EventEmitter
    # priority 和 FrameRef 的元組
    priority_queue: PriorityQueue[tuple[float, FrameRef]]
    ws_message_queue: Queue[Dict[str, Any]]


class BaseNode(Protocol):

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        """Initialize base node."""
        ...

    def prepare(self) -> None:
        """
        Prepare design resources for the node.
        """
        pass

    def setup(self, config: Dict[str, Any]) -> None:
        """
        Setup runtime configuration of the node.
        """
        pass

    def execute(self) -> Any:
        """
        Execute the node.
        """
        pass

    def next(self) -> None:
        """
        Next the node.
        """
        pass

    def dispose(self) -> None:
        """
        Dispose the node.
        """
        pass
