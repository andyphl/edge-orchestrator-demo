from typing import Any, Dict, List, Union, cast

from aiwin_resource.base import Resource, ResourceContext


class StringResource:
    """String resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        ctx_dict: Dict[str, Any] = dict(ctx)
        self.data: str = cast(str, ctx_dict['data'])
        self.scopes: List[str] = cast(List[str], ctx_dict['scopes'])
        self.name: str = cast(str, ctx_dict['name'])

    def get_sibling_resources(self) -> List[Resource]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': f"{'.'.join(self.scopes)}.{self.name}",
            'schema': 'string.v1',
            'name': self.name,
            'scopes': self.scopes,
        }]
