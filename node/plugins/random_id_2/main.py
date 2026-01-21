from typing import Any, Dict, cast

import cv2
from cv2.typing import MatLike

from aiwin_resource.base import Resource
from node.base import BaseNode, BaseNodeContext


class BinarizationNode(BaseNode):
    _binary_image_resource: Resource[MatLike] | None = None

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config

    def prepare(self) -> None:
        pass

    def setup(self, config: Dict[str, Any]) -> None:
        pass

    def execute(self) -> Any:
        cfg = self.cfg['config']
        image_resource = self.ctx['resource_manager'].get(cfg['image'])

        if image_resource is None:
            raise ValueError("Image resource is not found")

        image = cast(MatLike | None, image_resource.get_data())

        if image is None:
            raise ValueError("Image resource is not found")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        _, binary_image = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)

        self._binary_image_resource = self.ctx['resource_creator'].create('image.v1', {
            'name': 'binary_image',
            'scopes': [self.cfg['id']],
            'data': binary_image,
            "filename": f"{self.cfg['id']}_binary_image.jpg"
        })

        self.ctx['resource_manager'].set(
            self._binary_image_resource.get_key(), self._binary_image_resource)

    def next(self) -> None:
        next_node_index = self.cfg.get('_next_node_index')
        if next_node_index is not None:
            self.ctx['event'].emit(f"node_start_{next_node_index}")

    def dispose(self) -> None:
        if (self._binary_image_resource is not None):
            self._binary_image_resource.dispose()
