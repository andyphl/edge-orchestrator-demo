from typing import Any, Dict, Protocol, TypedDict

from aiwin_resource.instance_manager import ResourceInstanceManager
from aiwin_resource.creator import ResourceCreator
from event_emitter import EventEmitter
from store.file import BaseStore


class BaseNodeContext(TypedDict):
    resource_manager: ResourceInstanceManager
    resource_creator: ResourceCreator
    file_store: BaseStore
    event: EventEmitter


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

    def dispose(self) -> None:
        """
        Dispose the node.
        """
        pass
