from pathlib import Path
from typing import BinaryIO

from app.core.exceptions import NotFoundError
from app.integrations.storage.base import Storage


class LocalStorage(Storage):
    """Filesystem-backed storage rooted at a private directory.

    All keys are resolved beneath ``root`` so a crafted key can never escape the
    storage directory via path traversal.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError(f"Invalid storage key: {key}")
        return candidate

    def save(self, key: str, data: bytes) -> None:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    def open(self, key: str) -> BinaryIO:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError("Stored file not found")
        return path.open("rb")

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def path(self, key: str) -> Path:
        return self._resolve(key)
