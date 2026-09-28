"""Configuración cargada desde variables de entorno (.env). Nunca hay claves en el código."""

from functools import lru_cache

from pydantic import field_validator
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

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, value: str) -> str:
        # Render/Neon entregan "postgres://..." o "postgresql://..."; SQLAlchemy async necesita asyncpg.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix):]
        return value

    # Recuperación (valores de partida heredados del estimador; se validan con evals).
    retrieval_recall_k: int = 50
    rerank_top_n: int = 6
    rrf_k: int = 60
    # Rama léxica: descarta términos presentes en más de esta fracción de chunks
    # (filtro IDF) y pondera su aporte en la fusión. Calibrados con evals/.
    lexical_max_df: float = 0.15
    lexical_weight: float = 1.0

    # Agente: búsqueda que usan sus herramientas y tope de iteraciones del bucle.
    agent_search_mode: str = "hybrid"
    agent_rerank: bool = False
    agent_max_steps: int = 8

    # Protección del despliegue público (cada consulta gasta crédito real de la API).
    enable_cag: bool = False            # CAG cuesta ~US$1 por consulta sin caché: apagado en público
    requests_per_ip_per_hour: int = 10
    daily_budget_usd: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
