from typing import Any, Dict, Type, Union
from aiwin_resource.base import Resource, ResourceConfig, ResourceContext
from aiwin_resource.plugins.image.v1.main import ImageResource
from aiwin_resource.plugins.number.v1.main import NumberResource
from aiwin_resource.plugins.numbers.v1.main import NumbersResource
from aiwin_resource.plugins.string.v1.main import StringResource
from aiwin_resource.plugins.unknown.v1.main import UnknownResource
from aiwin_resource.plugins.vision.input.usb_device.v1.main import UsbDeviceResource
from aiwin_resource.plugins.vision.input.usb_devices.v1.main import UsbDevicesResource


class ResourceCreator:
    _registry: Dict[str, Type[Resource[Any]]] = {}

    def register(self, schema: str, resource: Type[Resource[Any]]) -> None:
        self._registry[schema] = resource

    def create(self, schema: str, config: Union[ResourceConfig, Dict[str, Any]]) -> Resource[Any]:
        resource_class = self._registry.get(schema)
        if resource_class is None:
            raise ValueError(f"Resource class for schema {schema} not found")

        ctx = ResourceContext(creator=self)
        return resource_class(ctx, config)


resource_creator = ResourceCreator()
resource_creator.register("image.v1", ImageResource)
resource_creator.register("string.v1", StringResource)
resource_creator.register("number.v1", NumberResource)
resource_creator.register("numbers.v1", NumbersResource)
resource_creator.register("unknown.v1", UnknownResource)
resource_creator.register("vision.input.usb_device.v1", UsbDeviceResource)
resource_creator.register("vision.input.usb_devices.v1", UsbDevicesResource)
