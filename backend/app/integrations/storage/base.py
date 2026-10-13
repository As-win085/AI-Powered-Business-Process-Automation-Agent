from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class Storage(ABC):
    """Interface for binary object storage used for uploaded documents.

    Objects are addressed by an opaque key (e.g. ``documents/<tenant>/<id>.pdf``)
    and are never exposed directly over HTTP; downloads must be authorized.
    """

    @abstractmethod
    def save(self, key: str, data: bytes) -> None:
        """Persist ``data`` under ``key``, overwriting any existing object."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open the object for binary reading."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether an object exists for ``key``."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the object for ``key`` if present."""

    @abstractmethod
    def path(self, key: str) -> Path:
        """Return the local filesystem path for ``key``.

        Only meaningful for filesystem-backed stores; other backends may raise
        NotImplementedError.
        """
