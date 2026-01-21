from typing import Any, Dict, List, Union, cast

from aiwin_resource.base import Resource, ResourceContext


class StringResource(Resource):
    """String resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        super().__init__(ctx)
        self.data: str = cast(str, ctx.get('data'))

    def get_sibling_resources(self) -> List[Resource]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': f"{'.'.join(self.scopes)}.{self.name}",
            'schema': 'string.v1',
            'timestamp': self.timestamp.isoformat(),
            'name': self.name,
            'data': self.data,
            'scopes': self.scopes,
        }]
