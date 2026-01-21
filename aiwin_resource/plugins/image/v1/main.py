from typing import Any, Dict, List, Union, cast

import cv2
import numpy as np
import requests
from cv2.typing import MatLike

from aiwin_resource.base import Resource, ResourceContext
from store.file import FileStore


class ImageResource(Resource):
    """Image resource implementation."""

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        super().__init__(ctx)
        # Convert numpy array (OpenCV frame) to JPEG bytes if needed
        image_data: Any = self.data
        if isinstance(image_data, np.ndarray):
            # OpenCV uses BGR, encode to JPEG

            success, encoded_image = cv2.imencode(
                '.jpg', cast(MatLike, image_data))
            if not success:
                raise ValueError("Failed to encode image to JPEG")
            image_data = encoded_image.tobytes()

        # just for demo purpose, DO NOT USE THIS IN PRODUCTION
        file_store = FileStore(cfg={"url": "http://localhost:8000"})
        response = file_store.upload("demo.jpg", image_data)
        self._filename = response['filename']

    def get_sibling_resources(self) -> List[Resource]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': f"{'.'.join(self.scopes)}.{self.name}",
            'schema': 'image.v1',
            'name': self.name,
            'scopes': self.scopes,
            'data': f"http://localhost:8000/file/{self._filename}"
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'ImageResource':
        return ImageResource({
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            # data will be image url, convert it to bytes
            'data': requests.get(serialized['data']).content
        })

    def dispose(self) -> None:
        file_store = FileStore(cfg={"url": "http://localhost:8000"})
        file_store.delete(self._filename)
