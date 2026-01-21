from typing import Any, Dict, List

import cv2

from aiwin_resource.plugins.image.v1.main import ImageResource
from aiwin_resource.plugins.vision.input.usb_devices.v1.main import \
    UsbDevicesResource
from node.base import BaseNode, BaseNodeContext


class WebcamNode(BaseNode):
    _image_resource: ImageResource | None = None

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

        # Check if device is available before attempting to open
        available_devices = self._list_devices()
        if device_id not in available_devices:
            raise ValueError(
                f"Device {device_id} is not available. "
                f"Available devices: {available_devices if available_devices else 'none'}. "
                f"Make sure the camera is connected and not in use by another application.")

        cap = cv2.VideoCapture(device_id)
        if not cap.isOpened():
            available_devices = self._list_devices()
            raise ValueError(
                f"Failed to open video capture for device {device_id}. "
                f"Available devices: {available_devices if available_devices else 'none'}. "
                f"The device may be in use by another application or may require permissions.")

        try:
            # Set some properties to help with initialization
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            ret, frame = cap.read()
            if not ret:
                raise ValueError(
                    f"Failed to read frame from device {device_id}. "
                    f"The camera may be in use, disconnected, or not responding. "
                    f"Try closing other applications that might be using the camera.")

            if frame.size == 0:
                raise ValueError(
                    f"Received empty frame from device {device_id}. "
                    f"The camera may not be providing valid video data.")

            self._image_resource = ImageResource({
                'name': 'image',
                'scopes': [self.cfg['id']],
                'data': frame,
                "filename": f"{self.cfg['id']}_image.jpg"
            })

            self.ctx['resource'].set(
                self._image_resource.get_key(), self._image_resource)

            # 执行完成后，通知下一个 node
            next_node_index = self.cfg.get('_next_node_index')
            if next_node_index is not None:
                self.ctx['event'].emit(f"node_start_{next_node_index}")
        finally:
            cap.release()

    def dispose(self) -> None:
        if (self._image_resource is not None):
            self._image_resource.dispose()
