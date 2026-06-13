"""Application configuration via Pydantic Settings.

All configuration is read from environment variables or a .env file.
No secrets are ever hardcoded.
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: two levels up from this file (backend/app/config.py → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────
    APP_NAME: str = "PrivateMailAI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = f"sqlite+aiosqlite:///{PROJECT_ROOT / 'data' / 'emails.db'}"

    # ── Ollama ───────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_CHAT_MODEL: str = "mistral:7b"
    OLLAMA_FAST_MODEL: str = "llama3.2:3b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT: int = 120
    OLLAMA_FAST_TIMEOUT: int = 30
    OLLAMA_DEEP_TIMEOUT: int = 120

    # ── ChromaDB ─────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "data" / "chroma")

    # ── IMAP defaults ────────────────────────────────────────────────────
    IMAP_TIMEOUT: int = 30
    IMAP_BATCH_SIZE: int = 50

    # ── CORS ─────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ── Security ─────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production"
    ENCRYPTION_KEY: str = ""

    # ── Sync settings ────────────────────────────────────────────────────
    SYNC_INTERVAL_MINUTES: int = 15
    MAX_EMAILS_PER_SYNC: int = 200

    # ── AI Processing ────────────────────────────────────────────────────
    AI_BATCH_SIZE: int = 10
    AI_MAX_RETRIES: int = 3

    # ── Prompt versioning ────────────────────────────────────────────────
    PROMPT_VERSION: str = "v1.0.0"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_env(cls, value: object) -> object:
        """Accept common deployment mode strings when DEBUG is inherited."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value


settings = Settings()
