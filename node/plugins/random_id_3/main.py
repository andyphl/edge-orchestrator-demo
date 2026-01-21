import random
from typing import Any, Dict

from aiwin_resource.plugins.number.v1.main import NumberResource
from node.base import BaseNode, BaseNodeContext


class RandomConditionNode(BaseNode):
    """隨機條件節點：產生隨機 0 或 1，用於循環條件判斷"""

    _number_resource: NumberResource[int] | None = None

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
        self._number_resource = NumberResource({
            'name': 'result',
            'scopes': [self.cfg['id']],
            'data': random_value
        })

        # 將 resource 存入 resource manager
        self.ctx['resource'].set(
            self._number_resource.get_key(), self._number_resource)

        # 返回隨機值，用於條件路由判斷
        # 注意：路由會由 main.py 中的 routing 配置自動處理
        return random_value

    def dispose(self) -> None:
        """清理資源"""
        if self._number_resource is not None:
            self._number_resource.dispose()
