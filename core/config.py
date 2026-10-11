"""Конфигурация приложения через pydantic-settings + YAML."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
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
        extra="ignore",
        protected_namespaces=(),
    )

    # ── API Keys ───────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    deepseek_api_key: str = Field(default="", validation_alias="DEEPSEEK_API_KEY")
    openai_default_model: str = Field(
        default="gpt-5.4", validation_alias="OPENAI_DEFAULT_MODEL"
    )
    openai_heavy_model: str = Field(
        default="gpt-5.5", validation_alias="OPENAI_HEAVY_MODEL"
    )

    # ── Vector DB ──────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite:///data/ai_office.db",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    worker_backend: str = Field(default="redis", validation_alias="WORKER_BACKEND")
    rq_queue_name: str = Field(default="ai_office_tasks", validation_alias="RQ_QUEUE_NAME")
    vector_backend: str = Field(default="pgvector", validation_alias="VECTOR_BACKEND")
    rag_default_top_k: int = Field(default=6, validation_alias="RAG_DEFAULT_TOP_K")
    embedding_provider: str = Field(default="fake", validation_alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="fake-embedding", validation_alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1536, validation_alias="EMBEDDING_DIMENSIONS")
    embedding_batch_size: int = Field(default=32, validation_alias="EMBEDDING_BATCH_SIZE")
    rag_lexical_fallback_enabled: bool = Field(
        default=True,
        validation_alias="RAG_LEXICAL_FALLBACK_ENABLED",
    )
    pgvector_similarity_metric: str = Field(
        default="cosine",
        validation_alias="PGVECTOR_SIMILARITY_METRIC",
    )
    local_vector_store_path: str = Field(
        default="data/vector_store/documents.jsonl",
        validation_alias="LOCAL_VECTOR_STORE_PATH",
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
    github_owner: str = Field(default="", validation_alias="GITHUB_OWNER")
    github_repo: str = Field(default="", validation_alias="GITHUB_REPO")
    jira_url: str = Field(default="", validation_alias="JIRA_URL")
    jira_user: str = Field(default="", validation_alias="JIRA_USER")
    jira_api_token: str = Field(default="", validation_alias="JIRA_API_TOKEN")

    # ── App ────────────────────────────────────────────────────────────
    ai_office_api_key: str = Field(default="", validation_alias="AI_OFFICE_API_KEY")
    ai_office_admin_token: str = Field(default="", validation_alias="AI_OFFICE_ADMIN_TOKEN")
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    app_name: str = Field(default="AI Office", validation_alias="APP_NAME")
    app_base_url: str = Field(default="http://localhost:8000", validation_alias="APP_BASE_URL")
    frontend_base_url: str = Field(
        default="http://localhost:3000",
        validation_alias="FRONTEND_BASE_URL",
    )
    generated_sites_root: str = Field(default="generated_sites", validation_alias="GENERATED_SITES_ROOT")
    generated_tools_root: str = Field(default="generated_tools", validation_alias="GENERATED_TOOLS_ROOT")
    ai_office_require_api_key: bool = Field(
        default=False, validation_alias="AI_OFFICE_REQUIRE_API_KEY"
    )
    ai_office_allowed_origins: str = Field(
        default="http://localhost:8000,http://localhost:5173,http://127.0.0.1:8000,http://127.0.0.1:5173",
        validation_alias="AI_OFFICE_ALLOWED_ORIGINS",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )
    default_cheap_model: str = Field(default="fake-cheap", validation_alias="DEFAULT_CHEAP_MODEL")
    default_mid_model: str = Field(default="fake-mid", validation_alias="DEFAULT_MID_MODEL")
    default_strong_model: str = Field(default="fake-strong", validation_alias="DEFAULT_STRONG_MODEL")
    model_provider_primary: str = Field(default="fake", validation_alias="MODEL_PROVIDER_PRIMARY")
    model_provider_fallback: str = Field(default="fake", validation_alias="MODEL_PROVIDER_FALLBACK")
    brain_provider: str = Field(default="fake", validation_alias="BRAIN_PROVIDER")
    brain_base_url: str = Field(default="", validation_alias="BRAIN_BASE_URL")
    brain_api_key: str = Field(default="", validation_alias="BRAIN_API_KEY")
    brain_cheap_model: str = Field(default="fake-cheap", validation_alias="BRAIN_CHEAP_MODEL")
    brain_strong_model: str = Field(default="fake-strong", validation_alias="BRAIN_STRONG_MODEL")
    brain_code_model: str = Field(default="fake-code", validation_alias="BRAIN_CODE_MODEL")
    enable_real_tools: bool = Field(default=False, validation_alias="ENABLE_REAL_TOOLS")
    enable_approval_required: bool = Field(default=True, validation_alias="ENABLE_APPROVAL_REQUIRED")
    enable_pii_redaction: bool = Field(default=True, validation_alias="ENABLE_PII_REDACTION")
    enable_cost_tracking: bool = Field(default=True, validation_alias="ENABLE_COST_TRACKING")
    enable_rag_citations: bool = Field(default=True, validation_alias="ENABLE_RAG_CITATIONS")
    ai_office_daily_budget_usd: str = Field(default="", validation_alias="AI_OFFICE_DAILY_BUDGET_USD")
    ai_office_monthly_budget_usd: str = Field(default="", validation_alias="AI_OFFICE_MONTHLY_BUDGET_USD")
    ai_office_budget_enforcement: str = Field(default="warn", validation_alias="AI_OFFICE_BUDGET_ENFORCEMENT")
    enable_pmo_agent: bool = Field(default=True, validation_alias="ENABLE_PMO_AGENT")
    enable_support_agent: bool = Field(default=True, validation_alias="ENABLE_SUPPORT_AGENT")
    enable_developer_agent: bool = Field(default=True, validation_alias="ENABLE_DEVELOPER_AGENT")
    enable_analyst_agent: bool = Field(default=True, validation_alias="ENABLE_ANALYST_AGENT")
    enable_copywriter_agent: bool = Field(default=True, validation_alias="ENABLE_COPYWRITER_AGENT")
    enable_strategist_agent: bool = Field(default=False, validation_alias="ENABLE_STRATEGIST_AGENT")
    enable_accountant_agent: bool = Field(default=False, validation_alias="ENABLE_ACCOUNTANT_AGENT")

    # ── Telegram access control ────────────────────────────────────────
    allowed_telegram_user_ids: str = Field(
        default="", validation_alias="ALLOWED_TELEGRAM_USER_IDS"
    )
    allowed_telegram_chat_ids: str = Field(
        default="", validation_alias="ALLOWED_TELEGRAM_CHAT_IDS"
    )
    telegram_allowed_chat_ids: str = Field(
        default="", validation_alias="TELEGRAM_ALLOWED_CHAT_IDS"
    )

    # ── Autonomous runtime ─────────────────────────────────────────────
    autonomy_enabled: bool = Field(default=False, validation_alias="AUTONOMY_ENABLED")
    autonomy_daily_plan_hour: int = Field(
        default=9, validation_alias="AUTONOMY_DAILY_PLAN_HOUR"
    )
    autonomy_evening_review_hour: int = Field(
        default=19, validation_alias="AUTONOMY_EVENING_REVIEW_HOUR"
    )
    autonomy_poll_interval_seconds: int = Field(
        default=1800, validation_alias="AUTONOMY_POLL_INTERVAL_SECONDS"
    )
    autonomy_timezone: str = Field(
        default="Asia/Almaty", validation_alias="AUTONOMY_TIMEZONE"
    )
    cron_secret: str = Field(default="", validation_alias="CRON_SECRET")
    ai_office_task_stuck_timeout_minutes: int = Field(
        default=30, validation_alias="AI_OFFICE_TASK_STUCK_TIMEOUT_MINUTES"
    )
    ai_office_task_max_retries: int = Field(
        default=2, validation_alias="AI_OFFICE_TASK_MAX_RETRIES"
    )
    ai_office_approval_ttl_hours: int = Field(
        default=24, validation_alias="AI_OFFICE_APPROVAL_TTL_HOURS"
    )

    # ── Safe developer tools ──────────────────────────────────────────
    ai_office_workspace_root: str = Field(
        default="workspaces", validation_alias="AI_OFFICE_WORKSPACE_ROOT"
    )
    ai_office_allow_file_writes: bool = Field(
        default=False, validation_alias="AI_OFFICE_ALLOW_FILE_WRITES"
    )
    ai_office_safe_commands: str = Field(
        default="pytest,python -m pytest,npm test,npm run build",
        validation_alias="AI_OFFICE_SAFE_COMMANDS",
    )
    ai_office_web_access_enabled: bool = Field(
        default=True, validation_alias="AI_OFFICE_WEB_ACCESS_ENABLED"
    )
    ai_office_web_search_max_results: int = Field(
        default=5, validation_alias="AI_OFFICE_WEB_SEARCH_MAX_RESULTS"
    )
    ai_office_web_fetch_max_chars: int = Field(
        default=6000, validation_alias="AI_OFFICE_WEB_FETCH_MAX_CHARS"
    )
    brave_search_api_key: str = Field(default="", validation_alias="BRAVE_SEARCH_API_KEY")

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid LOG_LEVEL: {v}")
        return v

    @field_validator("environment")
    @classmethod
    def _normalize_env(cls, v: str | Environment) -> Environment:
        if isinstance(v, Environment):
            return v
        return Environment(v.lower().strip())

    @field_validator("pgvector_similarity_metric")
    @classmethod
    def _normalize_pgvector_metric(cls, v: str) -> str:
        normalized = v.lower().strip()
        if normalized not in {"cosine", "inner_product"}:
            raise ValueError(f"Invalid PGVECTOR_SIMILARITY_METRIC: {v}")
        return normalized

    def require(self, *keys: str) -> None:
        """Raise if any required env vars are empty."""
        missing = [k for k in keys if not getattr(self, k, "").strip()]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

    def allowed_origins_list(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""
        return [
            origin.strip()
            for origin in self.ai_office_allowed_origins.split(",")
            if origin.strip()
        ]

    def safe_commands_list(self) -> list[str]:
        """Return allowlisted shell commands for the safe tools layer."""
        return [
            command.strip()
            for command in self.ai_office_safe_commands.split(",")
            if command.strip()
        ]


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
