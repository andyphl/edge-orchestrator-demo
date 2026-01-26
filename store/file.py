import os
from typing import Any, Dict, Protocol

import requests


class BaseStore(Protocol):
    def upload(self, filename: str, file: Any) -> Any:
        ...

    def download(self, filename: str) -> Any:
        ...

    def delete(self, filename: str) -> Any:
        ...


class FileStore(BaseStore):

    def __init__(self, cfg: Any):
        self.cfg: Dict[str, Any] | None = cfg

    def upload(self, filename: str, file: Any) -> Any:
        # Local fast-path: write into a directory on disk (no HTTP roundtrip).
        if self.cfg is None:
            raise ValueError("cfg is required")

        local_dir = self.cfg.get("local_dir")
        if local_dir is None:
            raise ValueError("local_dir is required")

        os.makedirs(local_dir, exist_ok=True)
        file_path = os.path.join(local_dir, filename)
        with open(file_path, "wb") as f:
            f.write(file)
        return {"filename": filename}

    def download(self, filename: str) -> Any:
        if self.cfg is None:
            raise ValueError("cfg is required")

        local_dir = self.cfg.get("local_dir")
        if local_dir:
            file_path = os.path.join(local_dir, filename)
            with open(file_path, "rb") as f:
                return f.read()
        return requests.get(f"{self.cfg['url']}/file/{filename}")

    def delete(self, filename: str) -> Any:
        if self.cfg is None:
            raise ValueError("cfg is required")
        local_dir = self.cfg.get("local_dir")
        if local_dir is None:
            raise ValueError("local_dir is required")
        if local_dir:
            file_path = os.path.join(local_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                return {"message": "File deleted"}
            return {"message": "File not found"}
        return requests.delete(f"{self.cfg['url']}/file/{filename}")
