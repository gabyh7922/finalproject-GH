"""Configuración cargada desde variables de entorno (.env). Nunca hay claves en el código."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Generación (CAG, RAG y agente). Ver README > "Elección de modelo".
    llm_model: str = "claude-opus-5"
    llm_effort: str = "medium"

    # Embeddings (mismo modelo que el estimador del curso).
    embedding_model: str = "text-embedding-3-small"

    database_url: str = "postgresql+asyncpg://lexlaboral:lexlaboral@localhost:5434/lexlaboral"

    # Recuperación (valores de partida heredados del estimador; se validan con evals).
    retrieval_recall_k: int = 50
    rerank_top_n: int = 6
    rrf_k: int = 60
    # Rama léxica: descarta términos presentes en más de esta fracción de chunks
    # (filtro IDF) y pondera su aporte en la fusión. Calibrados con evals/.
    lexical_max_df: float = 0.15
    lexical_weight: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
