from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and the root .env file."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI Business Automation"
    environment: str = "development"
    debug: bool = False
    api_base_path: str = "/api"
    log_level: str = "INFO"

    secret_key: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    database_url: str = "postgresql+psycopg://automation:automation@localhost:5432/automation"
    db_echo: bool = False

    redis_host: str = "localhost"
    redis_port: int = 6379
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    storage_root: Path = REPO_ROOT / "storage"
    max_upload_size_mb: int = 25
    allowed_upload_extensions: str = ".pdf,.png,.jpg,.jpeg"

    ocr_engine: str = "tesseract"
    tesseract_cmd: str | None = None
    ocr_languages: str = "eng"
    ocr_dpi: int = 200
    min_text_chars_per_page: int = 20
    ocr_max_pages: int = 50
    auto_process_documents: bool = True

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("storage_root", mode="after")
    @classmethod
    def _resolve_storage_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def allowed_upload_content_types(self) -> dict[str, tuple[str, ...]]:
        """Maps a file extension to the MIME types we accept for it."""

        return {
            ".pdf": ("application/pdf",),
            ".png": ("image/png",),
            ".jpg": ("image/jpeg",),
            ".jpeg": ("image/jpeg",),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
