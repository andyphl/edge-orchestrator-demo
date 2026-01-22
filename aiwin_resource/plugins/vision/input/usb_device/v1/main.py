from typing import Any, Dict, List, Union

from aiwin_resource.base import Resource, ResourceConfig, ResourceContext

"""
Schema:
{
    "schema": "vision.input.usb_device.v1",
    "kind": "primitive",
}
"""


class UsbDeviceResource(Resource[int]):
    """Usb device resource implementation."""
    schema: str = "vision.input.usb_device.v1"
    _siblings: List[Resource[Any]] = []

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return self._siblings

    def serialize(self) -> List[Dict[str, Any]]:
        item = self.get_item()
        if item is None:
            return []

        data = item.get('data')

        return [{
            'key': self._key,
            'schema': self.schema,
            'name': self._name,
            'scopes': self._scopes,
            'version': item.get('version'),
            'timestamp': item.get('timestamp').isoformat(),
            'data': data
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'UsbDeviceResource':
        return UsbDeviceResource(self._ctx, {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op
