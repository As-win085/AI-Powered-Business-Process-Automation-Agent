import secrets
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_prefix="", case_sensitive=False)

    environment: str = Field(default="development")
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    database_url: str = Field(default="postgresql+psycopg://postgres:postgres@localhost:5432/automation")
    db_echo: bool = False

    storage_root: Path = Field(default=Path("/tmp/automation_storage"))
    max_upload_mb: int = 25

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    tesseract_cmd: str | None = None
    ocr_dpi: int = 300
    ocr_languages: str = "eng"
    ocr_engine: Literal["tesseract"] = "tesseract"
    ocr_max_pages: int = 50

    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")
    auto_process_documents: bool = Field(default=True)

    app_name: str = "automation"
    api_base_path: str = ""
    jwt_algorithm: str = "HS256"
    refresh_token_expire_days: int = 7

    llm_provider: Literal["mock", "openai", "azure"] = Field(default="mock")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_timeout: int = 120
    llm_max_retries: int = 1
    llm_temperature: float = 0.0


settings = Settings()

