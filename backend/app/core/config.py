from functools import lru_cache
from pathlib import Path
from typing import Literal

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

    # LLM provider (external API behind a provider interface).
    llm_provider: Literal["mock", "openai", "azure"] = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_timeout: int = 120
    llm_max_retries: int = 1
    llm_temperature: float = 0.0

    # Approval routing policy (all configurable via environment variables).
    approval_manager_threshold: float = 1000.0
    approval_director_threshold: float = 10000.0
    approval_manager_role: str = "approver"
    approval_finance_role: str = "finance"
    approval_director_role: str = "admin"

    # Purchase order matching tolerances (all configurable via environment).
    po_match_amount_tolerance_abs: float = 0.01
    po_match_amount_tolerance_pct: float = 0.01
    po_match_price_tolerance_pct: float = 0.02
    po_match_quantity_tolerance_pct: float = 0.0

    # Anomaly detection (unsupervised Isolation Forest over supplier history).
    anomaly_feature_window_days: int = 30
    anomaly_flag_percentile: float = 90.0
    anomaly_contamination: float = 0.05
    anomaly_min_history: int = 3

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
    def anomaly_model_dir(self) -> Path:
        """Directory holding saved anomaly models, kept inside the storage root."""
        return self.storage_root / "models" / "anomaly"

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
