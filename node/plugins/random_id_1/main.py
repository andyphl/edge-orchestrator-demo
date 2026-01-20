from typing import Any, Dict, List

import cv2

from aiwin_resource.plugins.image.v1.main import ImageResource
from aiwin_resource.plugins.vision.input.usb_devices.v1.main import \
    UsbDevicesResource
from node.base import BaseNode, BaseNodeContext


class WebcamNode(BaseNode):

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config

    def _list_devices(self, max_devices: int = 10) -> List[int]:
        available: List[int] = []
        for i in range(max_devices):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available

    def prepare(self) -> None:
        # provide all available devices as resources
        devices = self._list_devices()

        use_devices_resource = UsbDevicesResource({
            'name': 'usb_devices',
            'scopes': [self.cfg['id']],
            'data': devices
        })
        self.ctx['resource'].set(
            use_devices_resource.get_key(), use_devices_resource)

    def setup(self, config: Dict[str, Any]) -> None:
        pass

    def execute(self) -> Any:
        device_id = self.cfg.get('config', {}).get('device_id')
        if device_id is None:
            raise ValueError("device_id is required")
        cap = cv2.VideoCapture(device_id)
        if not cap.isOpened():
            raise ValueError(
                f"Failed to open video capture for device {device_id}")
        try:
            ret, frame = cap.read()
            if not ret:
                raise ValueError(
                    f"Failed to read frame from device {device_id}")

            image_resource = ImageResource({
                'name': 'image',
                'scopes': [self.cfg['id']],
                'data': frame
            })

            self.ctx['resource'].set(
                image_resource.get_key(), image_resource)
        finally:
            cap.release()

    def dispose(self) -> None:
        pass
