from functools import lru_cache

from app.core.config import settings
from app.integrations.storage.base import Storage
from app.integrations.storage.local import LocalStorage


@lru_cache
def get_storage() -> Storage:
    """Return the configured storage backend.

    Only the local filesystem backend is implemented today; object storage
    (S3, GCS) is added in a later milestone behind this same interface.
    """
    return LocalStorage(settings.storage_root)
