from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config, loaded from environment / the stack .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    service_api_key: str

    gemini_api_key: str = ""

    rag_embed_model: str = "gemini-embedding-001"
    rag_embed_dims: int = 768
    rag_embed_batch: int = 64

    rag_gen_model: str = "gemini-3.1-flash-lite"
    rag_gen_temperature: float = 0.2

    rag_chunk_chars: int = 900
    rag_chunk_overlap: int = 150

    rag_candidates: int = 20
    rag_retrieve_k: int = 8
    rag_rrf_k0: int = 60

    rag_max_questions_per_day: int = 200
    rag_corpus_dir: str = "corpus"
    http_timeout: float = 60.0


settings = Settings()  # type: ignore[call-arg]
