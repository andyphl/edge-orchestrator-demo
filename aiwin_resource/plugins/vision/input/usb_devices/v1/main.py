from typing import Any, Dict, List, Union

from aiwin_resource.base import Resource, ResourceContext
from aiwin_resource.plugins.vision.input.usb_device.v1.main import \
    UsbDeviceResource


class UsbDevicesResource(Resource):
    """Usb devices resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        super().__init__(ctx)

        self._siblings: List[Resource] = []
        for device_id in self.data:
            self._siblings.append(UsbDeviceResource({
                'name': f"usb_device_{device_id}",
                'scopes': [*self.scopes, self.name],
                'data': device_id
            }))

    def get_sibling_resources(self) -> List[Resource]:
        return self._siblings

    def serialize(self) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = [{
            'key': self.key,
            'schema': 'vision.input.usb_devices.v1',
            'name': self.name,
            'timestamp': self.timestamp.isoformat(),
            'scopes': self.scopes,
            'data': self.data
        }]

        for sibling in self._siblings:
            serialized.extend(sibling.serialize())

        return serialized

    def from_serialized(self, serialized: Dict[str, Any]) -> 'UsbDevicesResource':
        return UsbDevicesResource({
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        for sibling in self._siblings:
            sibling.dispose()
