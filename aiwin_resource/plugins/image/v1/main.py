from typing import Any, Dict, List, Union, cast

import cv2
import requests
from cv2.typing import MatLike

from aiwin_resource.base import DataItem, Resource, ResourceConfig, ResourceContext
from store.file import FileStore


class ImageResource(Resource[MatLike]):
    """Image resource implementation."""
    schema: str = "image.v1"
    _file_store = FileStore(cfg={"url": "http://localhost:8000"})

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)
        self._filename: str = cast(str, config.get('filename', 'image.jpg'))

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        item = self.get_item()

        if item is None:
            return []

        data = item.get('data')

        versioned_filename = f"{self._version}_{self._filename}"
        if data is not None:
            success, encoded_image = cv2.imencode(
                '.jpg', data)
            if not success:
                raise ValueError("Failed to encode image to JPEG")
            image_data = encoded_image.tobytes()
            self._file_store.upload(
                versioned_filename, image_data)

        return [{
            'key': self._key,
            'schema': self.schema,
            'timestamp': item.get('timestamp').isoformat(),
            'version': item.get('version'),
            'name': self._name,
            'scopes': self._scopes,
            'data': f"http://localhost:8000/file/{versioned_filename}" if data is not None else None
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'ImageResource':
        return ImageResource(ResourceContext(event_emitter=self._ctx['event_emitter']), {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            # data will be image url, convert it to bytes
            'data': requests.get(serialized['data']).content
        })

    def dispose(self) -> None:

        self._file_store.delete(self._filename)

    def set_data(self, data: MatLike | None) -> DataItem:
        item = super().set_data(data)
        return item
