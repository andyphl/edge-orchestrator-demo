from typing import Any, Dict, List, Union, cast

from aiwin_resource.base import Resource, ResourceContext


class UsbDeviceResource(Resource):
    """Usb device resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        ctx_dict: Dict[str, Any] = dict(ctx)
        self.data: int = cast(int, ctx_dict['data'])
        self.scopes: List[str] = cast(List[str], ctx_dict['scopes'])
        self.name: str = cast(str, ctx_dict['name'])
        self.key: str = f"{'.'.join(self.scopes)}.{self.name}"

        self._siblings: List[Resource] = []

    def get_sibling_resources(self) -> List[Resource]:
        return self._siblings

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': f"{'.'.join(self.scopes)}.{self.name}",
            'schema': 'vision.input.usb_device.v1',
            'name': self.name,
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
