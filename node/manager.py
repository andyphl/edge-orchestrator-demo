from typing import Dict, Type

from node.base import BaseNode


class NodeManager:
    _registry: Dict[str, Type[BaseNode]] = {}

    def register(self, name: str, node: Type[BaseNode]) -> None:
        self._registry[name] = node

    def get(self, name: str) -> Type[BaseNode]:
        return self._registry[name]
