"""Cross-encoder reranker: recall-then-rerank (Sesión 10, reutilizado).

El bi-encoder (embeddings) compara vectores precalculados: rápido pero
mediocre ordenando. El cross-encoder lee pregunta y chunk *juntos* y puntúa la
relevancia real del par — más preciso, pero una inferencia por par, así que
solo reordena los candidatos ya recuperados, nunca el corpus entero.

Modelo multilingüe entrenado en mMARCO (incluye español):
`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`.
"""

from __future__ import annotations

import threading
import time

from app.observability import log_event

DEFAULT_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


class CrossEncoderReranker:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def load(self) -> None:
        self._ensure_loaded()

    def _ensure_loaded(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                t0 = time.perf_counter()
                self._model = CrossEncoder(self.model_name, max_length=512)
                log_event("reranker_loaded", model=self.model_name, load_ms=round((time.perf_counter() - t0) * 1000))
        return self._model

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        model = self._ensure_loaded()
        t0 = time.perf_counter()
        scores = model.predict([(query, t) for t in texts])
        log_event("reranker_scored", candidates=len(texts), score_ms=round((time.perf_counter() - t0) * 1000))
        return [float(s) for s in scores]
