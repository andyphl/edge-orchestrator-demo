from typing import Any, Dict, List, Union, cast

from aiwin_resource.base import Resource, ResourceContext
from aiwin_resource.plugins.vision.input.usb_device.v1.main import \
    UsbDeviceResource


class UsbDevicesResource(Resource):
    """Usb devices resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        ctx_dict: Dict[str, Any] = dict(ctx)
        self.data: List[int] = cast(List[int], ctx_dict['data'])
        self.scopes: List[str] = cast(List[str], ctx_dict['scopes'])
        self.name: str = cast(str, ctx_dict['name'])
        self.key: str = f"{'.'.join(self.scopes)}.{self.name}"

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
