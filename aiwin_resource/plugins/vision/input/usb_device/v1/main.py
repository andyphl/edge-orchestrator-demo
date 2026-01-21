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

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)

        self._siblings: List[Resource[Any]] = []

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return self._siblings

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': self._key,
            'schema': 'vision.input.usb_device.v1',
            'name': self._name,
            'timestamp': self._timestamp.isoformat(),
            'scopes': self._scopes,
            'data': self._data
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'UsbDeviceResource':
        return UsbDeviceResource(self._ctx, {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op
