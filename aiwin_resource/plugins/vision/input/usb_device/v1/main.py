from typing import Any, Dict, List, Union

from aiwin_resource.base import Resource, ResourceContext


class UsbDeviceResource(Resource):
    """Usb device resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        super().__init__(ctx)

        self._siblings: List[Resource] = []

    def get_sibling_resources(self) -> List[Resource]:
        return self._siblings

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': f"{'.'.join(self.scopes)}.{self.name}",
            'schema': 'vision.input.usb_device.v1',
            'name': self.name,
            'timestamp': self.timestamp.isoformat(),
            'scopes': self.scopes,
            'data': self.data
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'UsbDeviceResource':
        return UsbDeviceResource({
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op
