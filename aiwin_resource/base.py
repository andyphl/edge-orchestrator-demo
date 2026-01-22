from abc import abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Literal, Protocol, TypeVar, TypedDict, Union, cast


from aiwin_resource.utils import is_valid_resource_config
from event_emitter import EventEmitter


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
    """Resource context."""
    event_emitter: EventEmitter


class ResourceConfig(TypedDict):
    name: str
    scopes: List[str]
    data: Any | None
    pool_size: int | None


class DataToken(TypedDict):
    key: str
    version: int
    timestamp: str


class DataItem(TypedDict):
    data: Any | None
    version: int
    timestamp: datetime


class Resource(Generic[TData]):
    """Abstract resource class."""
    schema: str
    _ctx: ResourceContext
    _key: str
    _name: str
    _scopes: List[str]
    _pool: List[DataItem]
    _pool_size: int | None
    _siblings: List['Resource[Any]']
    _version: int = 0

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        self._ctx = ctx
        if (not is_valid_resource_config(config)):
            raise ValueError(f"Invalid config type: {config}")
        self._pool = []
        self._siblings = []
        self._name = cast(str, config.get('name'))
        self._scopes = cast(List[str], config.get('scopes'))
        self._pool_size = cast(int, config.get('pool_size', 5))
        self._key = f"{'.'.join(self._scopes)}.{self._name}"
        self.set_data(config.get('data', None))

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

    def create_token(self):
        """Create resource token."""
        item = self.get_item()
        if item is None:
            return None
        return DataToken(
            key=self._key,
            version=item['version'],
            timestamp=item['timestamp'].isoformat(),
        )

    def get_item(self, version: int | None = None) -> DataItem | None:
        """Get data item by version."""
        if version is None:
            return self._get_latest_item()
        return next((item for item in self._pool if item['version'] == version), None)

    def _get_latest_item(self) -> DataItem | None:
        """Get latest data item."""
        return self._pool[-1]

    def get_data(self, version: int | None = None) -> TData | None:
        """Get resource data."""
        item = self.get_item(version)
        if item is None:
            return None
        return item['data']

    def set_data(self, data: TData | None) -> DataItem:
        """Set resource data."""
        self._version += 1
        if self._pool_size is not None and len(self._pool) >= self._pool_size:
            self._pool.pop(0)
        item = DataItem(
            data=data,
            version=self._version,
            timestamp=datetime.now(),
        )
        self._pool.append(item)
        self._ctx['event_emitter'].emit(
            "resource_updated", self.create_token())
        return item

    def get_key(self) -> str:
        """Get resource key."""
        return self._key
