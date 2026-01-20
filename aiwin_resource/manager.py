from typing import Any, Dict, List

from aiwin_resource.base import Resource


class ResourceManager:
    _registry: Dict[str, Resource] = {}

    def set(self, key: str, resource: Resource) -> None:
        self._registry[key] = resource

    def get(self, key: str) -> Resource:
        return self._registry[key]

    def serialize(self) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for resource in self._registry.values():
            serialized.extend(resource.serialize())
        return serialized
