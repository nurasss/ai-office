"""Конфигурация приложения через pydantic-settings + YAML."""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class Settings(BaseSettings):
    """Глобальные настройки, загружаемые из .env и config/settings.yaml."""

    # ── API Keys ───────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    openai_default_model: str = Field(
        default="gpt-4o-mini", validation_alias="OPENAI_DEFAULT_MODEL"
    )
    openai_heavy_model: str = Field(
        default="gpt-4o", validation_alias="OPENAI_HEAVY_MODEL"
    )

    # ── Vector DB ──────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+psycopg2://user:password@localhost:5432/ai_office",
        validation_alias="DATABASE_URL",
    )
    pinecone_api_key: str = Field(default="", validation_alias="PINECONE_API_KEY")
    pinecone_index: str = Field(default="ai-office", validation_alias="PINECONE_INDEX")
    pinecone_env: str = Field(default="us-east-1", validation_alias="PINECONE_ENV")

    # ── External Tools ─────────────────────────────────────────────────
    slack_bot_token: str = Field(default="", validation_alias="SLACK_BOT_TOKEN")
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")
    github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")
    jira_url: str = Field(default="", validation_alias="JIRA_URL")
    jira_user: str = Field(default="", validation_alias="JIRA_USER")
    jira_api_token: str = Field(default="", validation_alias="JIRA_API_TOKEN")

    # ── App ────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

def load_agent_config() -> dict[str, Any]:
    """Загрузить YAML-конфигурацию агентов из config/settings.yaml."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton-доступ к настройкам."""
    return Settings()
