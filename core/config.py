"""Конфигурация приложения через pydantic-settings + YAML."""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class Settings(BaseSettings):
    """Глобальные настройки, загружаемые из .env и config/settings.yaml."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── API Keys ───────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    openai_default_model: str = Field(
        default="gpt-5.4", validation_alias="OPENAI_DEFAULT_MODEL"
    )
    openai_heavy_model: str = Field(
        default="gpt-5.5", validation_alias="OPENAI_HEAVY_MODEL"
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
    telegram_pmo_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_PMO_BOT_TOKEN"
    )
    telegram_data_analyst_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_DATA_ANALYST_BOT_TOKEN"
    )
    telegram_developer_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_DEVELOPER_BOT_TOKEN"
    )
    telegram_copywriter_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_COPYWRITER_BOT_TOKEN"
    )
    telegram_support_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_SUPPORT_BOT_TOKEN"
    )
    telegram_strategist_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_STRATEGIST_BOT_TOKEN"
    )
    telegram_accountant_bot_token: str = Field(
        default="", validation_alias="TELEGRAM_ACCOUNTANT_BOT_TOKEN"
    )
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")
    telegram_webhook_secret: str = Field(
        default="", validation_alias="TELEGRAM_WEBHOOK_SECRET"
    )
    telegram_general_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_GENERAL_THREAD_ID"
    )
    telegram_pmo_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_PMO_THREAD_ID"
    )
    telegram_data_analyst_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_DATA_ANALYST_THREAD_ID"
    )
    telegram_developer_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_DEVELOPER_THREAD_ID"
    )
    telegram_copywriter_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_COPYWRITER_THREAD_ID"
    )
    telegram_support_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_SUPPORT_THREAD_ID"
    )
    telegram_strategist_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_STRATEGIST_THREAD_ID"
    )
    telegram_accountant_thread_id: str = Field(
        default="", validation_alias="TELEGRAM_ACCOUNTANT_THREAD_ID"
    )
    github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")
    jira_url: str = Field(default="", validation_alias="JIRA_URL")
    jira_user: str = Field(default="", validation_alias="JIRA_USER")
    jira_api_token: str = Field(default="", validation_alias="JIRA_API_TOKEN")

    # ── App ────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )

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
