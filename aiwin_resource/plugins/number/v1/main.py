from typing import Any, Dict, List, Union

from aiwin_resource.base import Resource, ResourceContext


class NumberResource(Resource):
    """Number resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        super().__init__(ctx)

    def get_sibling_resources(self) -> List[Resource]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': f"{'.'.join(self.scopes)}.{self.name}",
            'schema': 'number.v1',
            'name': self.name,
            'timestamp': self.timestamp.isoformat(),
            'scopes': self.scopes,
            'data': self.data
        }]
