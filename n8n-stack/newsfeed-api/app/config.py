from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required
    database_url: str
    service_api_key: str

    # LLM enrichment
    llm_provider: str = "gemini"  # gemini | anthropic
    llm_max_tokens: int = 1024
    prompt_version: str = "v4"
    enrich_stale_hours: int = 48  # give up enriching / pushing news older than this

    # Gemini (free tier covers this workload)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    # Anthropic (only used when llm_provider=anthropic)
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5"

    # Fetching
    http_timeout: float = 20.0
    fetch_concurrency: int = 8
    fulltext_max_chars: int = 12000
    user_agent: str = "newsfeed-api/1.0 (personal research bot)"

    # Prices
    price_lookback_days_default: int = 7
    price_provider: str = "yahoo"  # yahoo | twelvedata (switched 2026-09-30: yfinance/Yahoo
    # has no hard daily cap, needed for 5-region scale (680 symbols); TwelveData's free
    # 800 credits/day would be exhausted almost immediately at this universe size)
    price_concurrency: int = 2
    twelvedata_api_key: str = ""

    # Telegram delivery
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    digest_max_items: int = 12
    digest_bullets_per_item: int = 2

    # Jev decision gate for importance re-check (breaking/notable/routine).
    # Runs as a cheap automatic confidence check on the LLM's own importance
    # call above — if Jev disagrees or isn't confident, the LLM's original
    # verdict is kept as-is (Jev never overrides silently, only flags).
    jev_decision_url: str = "http://jev-decision-server:8000"
    jev_escalate_below: float = 0.7
    jev_importance_gate_enabled: bool = True


settings = Settings()  # type: ignore[call-arg]
