from typing import Any, Dict, List, Union, cast

import cv2
import requests
from cv2.typing import MatLike

from aiwin_resource.base import DataItem, Resource, ResourceConfig, ResourceContext
from store.file import FileStore
from datetime import datetime


class ImageResource(Resource[MatLike]):
    """Image resource implementation."""
    schema: str = "image.v1"
    # Use local file store to avoid per-frame HTTP roundtrip to this same server.
    _file_store = FileStore(
        cfg={"url": "http://localhost:8000", "local_dir": "files"})

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

        # Overwrite a stable filename for "video-like" updates.
        # Add cache-bust query (?v=) so browsers re-fetch the latest frame.
        filename = self._filename
        if data is not None:
            success, encoded_image = cv2.imencode('.jpg', data, [
                int(cv2.IMWRITE_JPEG_QUALITY), 80
            ])
            if not success:
                raise ValueError("Failed to encode image to JPEG")
            image_data = encoded_image.tobytes()
            self._file_store.upload(filename, image_data)

        return [{
            'key': self._key,
            'schema': self.schema,
            'timestamp': item.get('timestamp').isoformat(),
            'version': item.get('version'),
            'name': self._name,
            'scopes': self._scopes,
            'data': f"http://localhost:8000/file/{filename}?v={item.get('version')}" if data is not None else None
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
        """Override set_data to upload image to file store."""
        self._version += 1
        if self._pool_size is not None and len(self._pool) >= self._pool_size:
            self._pool.pop(0)
            # self._file_store.delete(
            #     f"{popped_item['version']}_{self._filename}")
        item = DataItem(
            data=data,
            version=self._version,
            timestamp=datetime.now(),
        )
        self._pool.append(item)
        self._ctx['event_emitter'].emit(
            "resource_updated", self.create_token())
        return item
