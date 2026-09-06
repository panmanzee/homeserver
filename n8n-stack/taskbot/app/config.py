"""Runtime configuration, loaded from environment / the stack .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required
    database_url: str
    service_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str

    # LLM — provider is pluggable (mirrors newsfeed-api). Gemini is the default:
    # free tier covers this workload and the stack .env already has a live key.
    llm_provider: str = "gemini"          # gemini | anthropic
    gemini_api_key: str = ""
    # flash-lite: a per-message chat workload wants the high free-tier request/day
    # cap. Override with TASKBOT_GEMINI_MODEL (see docker-compose.yml).
    gemini_model: str = "gemini-3.1-flash-lite"
    anthropic_api_key: str = ""           # only needed when llm_provider = anthropic
    claude_model: str = "claude-haiku-4-5"
    llm_max_tokens: int = 1024

    # Behaviour
    taskbot_tz: str = "UTC"
    taskbot_morning_time: str = "07:30"
    taskbot_evening_time: str = "21:00"
    http_timeout: float = 35.0
    taskbot_run_workers: bool = True   # binds to TASKBOT_RUN_WORKERS; tests set it false to skip poller+scheduler
    taskbot_log_retention_days: int = 30   # message_log rows older than this are pruned nightly

    # Google Calendar (all optional — service runs without them)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_calendar_id: str = ""


settings = Settings()  # type: ignore[call-arg]
