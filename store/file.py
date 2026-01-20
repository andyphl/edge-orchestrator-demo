from typing import Any, Protocol

import requests


class BaseStore(Protocol):
    def upload(self, filename: str, file: Any) -> Any:
        ...

    def download(self, filename: str) -> Any:
        ...


class FileStore(BaseStore):

    def __init__(self, cfg: Any):
        self.cfg = cfg

    def upload(self, filename: str, file: Any) -> Any:
        # Handle bytes by wrapping in a tuple with the filename
        if isinstance(file, bytes):
            file_data = (filename, file)
        else:
            file_data = file

        response = requests.post(
            f"{self.cfg['url']}/file",
            files={"file": file_data},
            data={"filename": filename}
        )
        if response.status_code != 200:
            raise Exception(f"Failed to upload file: {response.text}")
        return response.json()

    def download(self, filename: str) -> Any:
        return requests.get(f"{self.cfg['url']}/file/{filename}")
