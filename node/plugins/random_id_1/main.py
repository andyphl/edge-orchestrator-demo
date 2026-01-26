from typing import Any, Dict, List

import cv2
from cv2.typing import MatLike

from aiwin_resource.base import Resource
from node.base import BaseNode, BaseNodeContext


class WebcamNode(BaseNode):
    _image_resource: Resource[MatLike] | None = None
    _cap: cv2.VideoCapture | None = None
    _is_valid_device: bool = False

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config

        self._image_resource = self.ctx['resource_creator'].create('image.v1', {
            'name': 'image',
            'scopes': [self.cfg['id']],
            'data': None,
            "filename": f"{self.cfg['id']}_image.jpg"
        })
        self.ctx['resource_manager'].set(
            self._image_resource.get_key(), self._image_resource)

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

        use_devices_resource = self.ctx['resource_creator'].create('vision.input.usb_devices.v1', {
            'name': 'usb_devices',
            'scopes': [self.cfg['id']],
            'data': devices,
        })
        self.ctx['resource_manager'].set(
            use_devices_resource.get_key(), use_devices_resource)

    def setup(self, config: Dict[str, Any]) -> None:
        pass

    def execute(self) -> Any:
        device_id = self.cfg.get('config', {}).get('device_id')
        if device_id is None:
            raise ValueError("device_id is required")

        # Check if device is available before attempting to open
        if not self._is_valid_device:
            available_devices = self._list_devices()
            if device_id not in available_devices:
                raise ValueError(
                    f"Device {device_id} is not available. "
                    f"Available devices: {available_devices if available_devices else 'none'}. "
                    f"Make sure the camera is connected and not in use by another application.")
            self._is_valid_device = True

        # Reuse VideoCapture across executions (opening the camera per-frame is expensive
        # and can leak handles if not released).
        if self._cap is None or not self._cap.isOpened():
            self._cap = cv2.VideoCapture(device_id)
            if not self._cap.isOpened():
                raise ValueError(
                    f"Failed to open video capture for device {device_id}. "
                    f"The device may be in use by another application or may require permissions.")

        try:
            # Keep buffer small to reduce latency
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            ret, frame = self._cap.read()
            if not ret:
                raise ValueError(
                    f"Failed to read frame from device {device_id}. "
                    f"The camera may be in use, disconnected, or not responding. "
                    f"Try closing other applications that might be using the camera.")

            if frame.size == 0:
                raise ValueError(
                    f"Received empty frame from device {device_id}. "
                    f"The camera may not be providing valid video data.")

            if self._image_resource is not None:
                self._image_resource.set_data(frame)

            else:
                self._image_resource = self.ctx['resource_creator'].create('image.v1', {
                    'name': 'image',
                    'scopes': [self.cfg['id']],
                    'data': frame,
                    "filename": f"{self.cfg['id']}_image.jpg"
                })

            self.ctx['resource_manager'].set(
                self._image_resource.get_key(), self._image_resource)

            # 执行完成后，通知下一个 node

        except Exception as e:
            # If capture breaks, release so next execute can reopen cleanly.
            try:
                # At this point `_cap` is expected to be initialized.
                self._cap.release()
            finally:
                self._cap = None
                self._is_valid_device = False
            raise e

    def next(self) -> None:
        next_node_index = self.cfg.get('_next_node_index')
        if next_node_index is not None:
            self.ctx['event'].emit(f"node_start_{next_node_index}")

    def dispose(self) -> None:
        if self._cap is not None:
            self._cap.release()
        if (self._image_resource is not None):
            self._image_resource.dispose()
