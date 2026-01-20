from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Protocol, TypedDict, Union


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


class ResourceProtocol(Protocol):
    """Resource protocol interface."""

    def get_sibling_resources(self) -> List['Resource']:
        """Get child resources."""
        ...

    def serialize(self) -> List[Dict[str, Any]]:
        """Serialize resource to representable data."""
        ...

    def get_key(self) -> str:
        """Get resource key."""
        ...


class ResourceContext(TypedDict):
    name: str
    scopes: List[str]
    data: Any


class Resource(ABC):
    """Abstract resource class."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        ctx_dict: Dict[str, Any] = dict(ctx)
        self.data: Any = ctx_dict['data']
        self.scopes: List[str] = ctx_dict['scopes']
        self.name: str = ctx_dict['name']
        self.key: str = f"{'.'.join(self.scopes)}.{self.name}"

    @abstractmethod
    def get_sibling_resources(self) -> List['Resource']:
        """Get child resources."""
        ...

    @abstractmethod
    def serialize(self) -> List[Dict[str, Any]]:
        """Serialize resource to representable data."""
        ...

    @abstractmethod
    def from_serialized(self, serialized: Dict[str, Any]) -> 'Resource':
        """Create resource from serialized data."""
        ...

    def set_data(self, data: Any) -> None:
        """Set resource data."""
        self.data = data

    def get_data(self) -> Any:
        """Get resource data."""
        return self.data

    def get_key(self) -> str:
        """Get resource key."""
        return self.key
