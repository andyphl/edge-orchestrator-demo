from typing import Any, Dict, Type, Union
from aiwin_resource.base import Resource, ResourceConfig


class ResourceCreator:
    _registry: Dict[str, Type[Resource[Any]]] = {}

    def register(self, schema: str, resource: Type[Resource[Any]]) -> None:
        self._registry[schema] = resource

    def create(self, schema: str, config: Union[ResourceConfig, Dict[str, Any]]) -> Resource[Any]:
        resource_class = self._registry.get(schema)
        if resource_class is None:
            raise ValueError(f"Resource class for schema {schema} not found")

        return resource_class({}, config)
