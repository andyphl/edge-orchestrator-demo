from typing import Protocol


class Disposable(Protocol):
    def dispose(self) -> None:
        """
        Dispose the disposable.
        """
        pass
