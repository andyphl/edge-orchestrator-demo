from typing import Any, Dict, cast

import cv2
from cv2.typing import MatLike

from aiwin_resource.plugins.image.v1.main import ImageResource
from node.base import BaseNode, BaseNodeContext


class BinarizationNode(BaseNode):
    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config

    def prepare(self) -> None:
        pass

    def setup(self, config: Dict[str, Any]) -> None:
        pass

    def execute(self) -> Any:
        cfg = self.cfg['config']
        image_resource = self.ctx['resource'].get(cfg['image'])

        image = image_resource.get_data()
        gray = cast(MatLike, cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    if len(image.shape) == 3 else image)
        _, binary_image = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)

        binary_image_resource = ImageResource({
            'name': 'binary_image',
            'scopes': [self.cfg['id']],
            'data': binary_image
        })

        self.ctx['resource'].set(
            binary_image_resource.get_key(), binary_image_resource)

        # 执行完成后，通知下一个 node
        next_node_index = self.cfg.get('_next_node_index')
        if next_node_index is not None:
            self.ctx['event'].emit(f"node_start_{next_node_index}")
