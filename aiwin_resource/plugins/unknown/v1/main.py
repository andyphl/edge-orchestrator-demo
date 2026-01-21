from typing import Any, Callable, Dict, List, Union

from aiwin_resource.base import Resource, ResourceConfig, ResourceContext

"""
{
    "schema": "unknown.v1",
    "kind": "primitive",
}
"""


class UnknownResource(Resource[Any]):
    schema: str = "unknown.v1"

    _serialize_fn: Callable[[Any], Any] | None = None

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)
        self._serialize_fn = ctx.get('serialize_fn')

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        if self._serialize_fn is None:
            raise ValueError("serialize_fn is not set")
        return [{
            'key': self._key,
            'schema': 'unknown.v1',
            'name': self._name,
            'timestamp': self._timestamp.isoformat(),
            'scopes': self._scopes,
            'data': self._serialize_fn(self._data)
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'UnknownResource':
        return UnknownResource(self._ctx, {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op
