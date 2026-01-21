from typing import Any, Dict, List, Union, cast

import cv2
import numpy as np
import requests
from cv2.typing import MatLike

from aiwin_resource.base import Resource, ResourceConfig, ResourceContext
from store.file import FileStore


class ImageResource(Resource[MatLike]):
    """Image resource implementation."""
    _file_store = FileStore(cfg={"url": "http://localhost:8000"})

    def __init__(self, ctx: ResourceContext, config: Union[ResourceConfig, Dict[str, Any]]):
        super().__init__(ctx, config)
        # Convert numpy array (OpenCV frame) to JPEG bytes if needed
        self._filename: str = cast(str, config.get('filename', 'image.jpg'))

        if isinstance(self._data, np.ndarray):
            # OpenCV uses BGR, encode to JPEG

            success, encoded_image = cv2.imencode(
                '.jpg', self._data)
            if not success:
                raise ValueError("Failed to encode image to JPEG")
            image_data = encoded_image.tobytes()
            # """
            # Just for demo purpose, DO NOT USE THIS IN PRODUCTION, serialize strategy
            # should be injectable, so that we can use different file store for different
            # environments, e.g. local file store, s3 file store, base64 etc.
            # """
            # self._file_store.upload(self._filename, image_data)

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:
        return [{
            'key': self._key,
            'schema': 'image.v1',
            'timestamp': self._timestamp.isoformat(),
            'name': self._name,
            'scopes': self._scopes,
            'data': f"http://localhost:8000/file/{self._filename}"
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'ImageResource':

        return ImageResource({}, {
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            # data will be image url, convert it to bytes
            'data': requests.get(serialized['data']).content
        })

    def dispose(self) -> None:

        self._file_store.delete(self._filename)

    def set_data(self, data: MatLike) -> None:
        super().set_data(data)
        # 使用更安全的類型檢查，避免 MatLike Protocol 導致的遞歸錯誤
        # 直接檢查是否有 shape 屬性（numpy array 和 OpenCV Mat 都有）
        if self._data is not None and hasattr(self._data, 'shape') and hasattr(self._data, 'dtype'):
            try:
                # OpenCV uses BGR, encode to JPEG
                # 使用 Any 類型避免類型檢查問題
                image_data_any: Any = self._data
                success, encoded_image = cv2.imencode('.jpg', image_data_any)
                if not success:
                    raise ValueError("Failed to encode image to JPEG")
                image_data = encoded_image.tobytes()
                self._file_store.upload(self._filename, image_data)
            except Exception as e:
                # 如果上傳失敗，記錄但不影響主流程
                print(f"Warning: Failed to upload image to file store: {e}")
