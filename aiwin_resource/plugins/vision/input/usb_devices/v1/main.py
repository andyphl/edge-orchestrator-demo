from typing import Any, Dict, List, Union

from aiwin_resource.base import Resource, ResourceConfig, ResourceContext
from aiwin_resource.plugins.vision.input.usb_device.v1.main import \
    UsbDeviceResource


"""
Schema:
{
    "schema": "vision.input.usb_devices.v1",
    "kind": "collection",
    "items": "vision.input.usb_device.v1",
}
"""


class UsbDevicesResource(Resource[List[int]]):
    """Usb devices resource implementation."""
    schema: str = "vision.input.usb_devices.v1"
    _siblings: List[Resource[int]] = []

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)

        if self._data is None:
            return

        for device_id in self._data:
            self._siblings.append(UsbDeviceResource(self._ctx, {
                'name': f"usb_device_{device_id}",
                'scopes': [*self._scopes, self._name],
                'data': device_id
            }))

    def get_sibling_resources(self) -> List[Resource[int]]:
        return self._siblings

    def serialize(self) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = [{
            'key': self._key,
            'schema': 'vision.input.usb_devices.v1',
            'name': self._name,
            'timestamp': self._timestamp.isoformat(),
            'scopes': self._scopes,
            'data': self._data
        }]

        for sibling in self._siblings:
            serialized.extend(sibling.serialize())

        return serialized

    def from_serialized(self, serialized: Dict[str, Any]) -> 'UsbDevicesResource':
        return UsbDevicesResource(self._ctx, {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        for sibling in self._siblings:
            sibling.dispose()
