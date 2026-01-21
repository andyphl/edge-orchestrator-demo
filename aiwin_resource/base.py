from abc import abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Literal, Protocol, TypeVar, TypedDict, Union

from aiwin_resource.creator import ResourceCreator


class BaseSchema(TypedDict, total=False):
    schema: str
    extends: List[str]


class PrimitiveSchema(BaseSchema):
    kind: Literal['primitive']


class ObjectSchema(BaseSchema):
    kind: Literal['object']
    props: Dict[str, str]


class CollectionSchema(BaseSchema):
    kind: Literal['collection']
    items: str


Schema = Union[PrimitiveSchema, ObjectSchema, CollectionSchema]


TData = TypeVar('TData')


class ResourceProtocol(Generic[TData], Protocol):
    """Resource protocol interface."""

    def get_sibling_resources(self) -> List['Resource[TData]']:
        """Get child resources."""
        ...

    def serialize(self) -> List[Dict[str, Any]]:
        """Serialize resource to representable data."""
        ...

    def get_key(self) -> str:
        """Get resource key."""
        ...


class ResourceContext(TypedDict):
    creator: ResourceCreator


class ResourceConfig(TypedDict):
    name: str
    scopes: List[str]
    data: Any | None


class Resource(Generic[TData]):
    """Abstract resource class."""
    schema: str
    _ctx: ResourceContext
    _key: str
    _name: str
    _scopes: List[str]
    _data: TData | None = None
    _siblings: List['Resource[Any]'] = []
    _timestamp: datetime

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        self._ctx = ctx
        self._name = config['name']
        self._scopes = config['scopes']
        self._key = f"{'.'.join(self._scopes)}.{self._name}"
        self._data = config['data']
        self._timestamp = datetime.now()

    @abstractmethod
    def get_sibling_resources(self) -> List['Resource[Any]']:
        """Get child resources."""
        ...

    @abstractmethod
    def serialize(self) -> List[Dict[str, Any]]:
        """Serialize resource to representable data."""
        ...

    @abstractmethod
    def from_serialized(self, serialized: Dict[str, Any]) -> 'Resource[TData]':
        """Create resource from serialized data."""
        ...

    @abstractmethod
    def dispose(self) -> None:
        """Dispose resource."""
        ...

    def set_data(self, data: TData) -> None:
        """Set resource data."""
        self._data = data

    def get_data(self) -> TData | None:
        """Get resource data."""
        return self._data

    def get_key(self) -> str:
        """Get resource key."""
        return self._key
