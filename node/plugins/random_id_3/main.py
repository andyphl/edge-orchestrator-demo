import random
from typing import Any, Dict

from aiwin_resource.base import Resource
from node.base import BaseNode, BaseNodeContext


class RandomConditionNode(BaseNode):
    """隨機條件節點：產生隨機 0 或 1，用於循環條件判斷"""

    _number_resource: Resource[int] | None = None

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config

    def prepare(self) -> None:
        """準備階段：無需特殊準備"""
        pass

    def setup(self, config: Dict[str, Any]) -> None:
        """設置階段：無需特殊設置"""
        pass

    def execute(self) -> Any:
        """
        執行節點：產生隨機 0 或 1

        Returns:
            int: 隨機產生的值（0 或 1），用於條件路由判斷
        """
        # 產生隨機 0 或 1
        random_value = random.randint(0, 1)

        # 創建 NumberResource
        self._number_resource = self.ctx['resource_creator'].create('number.v1', {
            'name': 'result',
            'scopes': [self.cfg['id']],
            'data': random_value
        })

        # 將 resource 存入 resource manager
        self.ctx['resource_manager'].set(
            self._number_resource.get_key(), self._number_resource)

    def next(self) -> None:
        next_node_index = self.cfg.get('_next_node_index')
        next_index = next_node_index if next_node_index is not None else 0  # 最後一節點循環回 0
        self.ctx['event_queue'].put({"next_node_index": next_index})

    def dispose(self) -> None:
        """清理資源"""
        if self._number_resource is not None:
            self._number_resource.dispose()
