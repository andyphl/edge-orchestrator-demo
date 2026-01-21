from typing import Any, Dict, List, TypeVar, Union

from aiwin_resource.base import Resource, ResourceConfig, ResourceContext


"""
Schema:
{
    "schema": "number.v1",
    "kind": "primitive",
}
"""

TData = TypeVar('TData', float, int, complex)


class NumberResource(Resource[TData]):
    """Number resource implementation."""
    schema: str = "number.v1"

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)
        self._generate_siblings = ctx.get('generate_siblings', False)

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': f"{'.'.join(self._scopes)}.{self._name}",
            'schema': 'number.v1',
            'name': self._name,
            'timestamp': self._timestamp.isoformat(),
            'scopes': self._scopes,
            'data': self._data
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'NumberResource[TData]':
        return NumberResource(self._ctx, {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op
