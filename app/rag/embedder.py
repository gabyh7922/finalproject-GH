"""Embeddings de OpenAI (`text-embedding-3-small`, 1536 dim) — igual que el estimador.

Batches de 100 textos por llamada y reintento exponencial ante rate limit.
"""

from __future__ import annotations

import time
from functools import lru_cache

from app.config import get_settings
from app.observability import log_event

PRICE_PER_MILLION_TOKENS_USD = 0.02
_BATCH_SIZE = 100
_RETRY_WAITS_SECONDS = [1, 2, 4]


@lru_cache
def _client():
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el entorno (.env).")
    return OpenAI(api_key=settings.openai_api_key)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    from openai import RateLimitError

    for attempt in range(len(_RETRY_WAITS_SECONDS) + 1):
        try:
            response = _client().embeddings.create(model=get_settings().embedding_model, input=texts)
            return [item.embedding for item in response.data]
        except RateLimitError:
            if attempt == len(_RETRY_WAITS_SECONDS):
                raise
            time.sleep(_RETRY_WAITS_SECONDS[attempt])
    raise RuntimeError("unreachable")  # pragma: no cover


def embed_one(text: str) -> list[float]:
    return _embed_batch([text])[0]


def embed_many(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        t0 = time.perf_counter()
        vectors.extend(_embed_batch(batch))
        log_event("embedding_batch", size=len(batch), latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    return vectors
