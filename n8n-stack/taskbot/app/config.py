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
    anthropic_api_key: str

    # LLM
    claude_model: str = "claude-haiku-4-5"
    llm_max_tokens: int = 1024

    # Behaviour
    taskbot_tz: str = "UTC"
    taskbot_morning_time: str = "07:30"
    taskbot_evening_time: str = "21:00"
    http_timeout: float = 35.0
    run_workers: bool = True   # tests set TASKBOT_RUN_WORKERS=false to skip poller+scheduler

    # Google Calendar (all optional — service runs without them)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_calendar_id: str = ""


settings = Settings()  # type: ignore[call-arg]
