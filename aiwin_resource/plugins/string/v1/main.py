from typing import Any, Dict, List, Union, cast

from aiwin_resource.base import Resource, ResourceConfig, ResourceContext

"""
{
    "schema": "string.v1",
    "kind": "primitive",
}
"""


class StringResource(Resource[str]):
    """String resource implementation."""
    schema: str = "string.v1"

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)
        self.data: str = cast(str, ctx.get('data'))

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': self._key,
            'schema': 'string.v1',
            'timestamp': self._timestamp.isoformat(),
            'name': self._name,
            'data': self.get_data(),
            'scopes': self._scopes,
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'StringResource':
        return StringResource(self._ctx, {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op
