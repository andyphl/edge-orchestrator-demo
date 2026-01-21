from typing import Any, Dict, List, Union, cast

from aiwin_resource.base import Resource, ResourceContext

"""
{
    "schema": "string.v1",
    "kind": "primitive",
}
"""


class StringResource(Resource[str]):
    """String resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        super().__init__(ctx)
        self.data: str = cast(str, ctx.get('data'))

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': self._key,
            'schema': 'string.v1',
            'timestamp': self._timestamp.isoformat(),
            'name': self._name,
            'data': self._data,
            'scopes': self._scopes,
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'StringResource':
        return StringResource({
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op
