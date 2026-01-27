from typing import Any, Callable, Dict, Protocol, TypedDict

from aiwin_resource.instance_manager import ResourceInstanceManager
from aiwin_resource.creator import ResourceCreator
from event_emitter import EventEmitter
from event_queue.base import EventQueue
from store.file import BaseStore


class NodeToken(TypedDict, total=False):
    """Token put into the event queue to schedule the next node.

    - next_node_index: index of the node to run (required).
    - Future: condition, jump_target, payload for conditional routing.
    """
    next_node_index: int


class _BaseNodeContextRequired(TypedDict):
    resource_manager: ResourceInstanceManager
    resource_creator: ResourceCreator
    file_store: BaseStore
    event: EventEmitter
    event_queue: EventQueue


class BaseNodeContext(_BaseNodeContextRequired, total=False):
    """When set, nodes put a token into the queue instead of emitting node_start_*."""
    put_token: Callable[[NodeToken], None]


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
