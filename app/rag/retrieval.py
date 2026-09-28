"""Recuperación recall-then-rerank (Sesión 10) sobre el Código del Trabajo.

Dos interruptores, igual que en el estimador, para poder medir cada técnica:

* `search_mode="vector"`  — solo k-NN denso (coseno, índice HNSW).
* `search_mode="hybrid"`  — rama vectorial + rama léxica (`embed_tsv`, español),
  fusionadas con Reciprocal Rank Fusion.
* `rerank=True`           — recupera ANCHO (`recall_k`) y el cross-encoder deja
  los `top_n` mejores.

Por qué híbrida en un corpus legal: las preguntas mezclan lenguaje coloquial
("me echaron", "vacaciones") —donde gana el vector— con términos técnicos
exactos ("fuero maternal", "artículo 161", "desahucio") —donde gana la búsqueda
léxica—. RRF combina ambos rankings sin calibrar puntuaciones.

Configuración por defecto = la que ganó en evals/results/retrieval.md:
vectorial sin reranking (hit@5 0,94, MRR 0,74, 12 ms). Híbrida y reranking
quedan disponibles para experimentar (y la híbrida para el agente, que busca
con vocabulario del Código).

Al final se **deduplica por artículo**: si dos partes del mismo artículo
entran al top, cuentan como un solo resultado (la unidad de citación es el
artículo, y el generador recibe el artículo completo — "small-to-big").
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.observability import log_event
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.models import ChunkRow
from app.rag.reranker import CrossEncoderReranker


@dataclass
class RetrievedChunk:
    chunk_id: str
    article_id: str
    content: str
    embed_text: str
    metadata: dict
    distance: float | None = None
    rerank_score: float | None = None
    sources: list[str] = field(default_factory=list)  # ramas que lo encontraron: vector / lexical


@lru_cache
def get_default_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker()


_COLUMNS = (ChunkRow.chunk_id, ChunkRow.article_id, ChunkRow.content, ChunkRow.embed_text, ChunkRow.chunk_metadata)


async def _search_vector(session: AsyncSession, query_vector: list[float], limit: int):
    # ef_search por defecto (40) limita cuántos vecinos devuelve HNSW; se sube para recall ancho.
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {max(40, limit)}"))
    distance = ChunkRow.embedding.cosine_distance(query_vector)
    stmt = select(*_COLUMNS, distance.label("distance")).order_by(distance).limit(limit)
    return (await session.execute(stmt)).all()


async def _search_lexical(session: AsyncSession, query_text: str, limit: int):
    # websearch_to_tsquery exige TODOS los términos (AND) y las preguntas coloquiales
    # tienen muchas palabras: casi nunca calzan todas. Se usa OR entre términos y
    # ts_rank_cd premia a los chunks que calzan más de ellos. Postgres descarta las
    # stopwords y aplica stemming en español.
    lexemes = await _discriminative_lexemes(session, query_text)
    if not lexemes:
        return []
    tsquery = func.to_tsquery("simple", " | ".join(lexemes))
    rank = func.ts_rank_cd(ChunkRow.embed_tsv, tsquery)
    stmt = (
        select(*_COLUMNS, rank.label("rank"))
        .where(ChunkRow.embed_tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).all()


_doc_freq: dict[str, int] = {}
_total_chunks = 0


async def _load_doc_freq(session: AsyncSession) -> None:
    """Frecuencia documental de cada lexema del índice (una vez por proceso)."""
    global _total_chunks
    if _doc_freq:
        return
    rows = (await session.execute(text("SELECT word, ndoc FROM ts_stat('SELECT embed_tsv FROM chunks')"))).all()
    _doc_freq.update({r.word: r.ndoc for r in rows})
    _total_chunks = await session.scalar(select(func.count()).select_from(ChunkRow)) or 1


async def _discriminative_lexemes(session: AsyncSession, query_text: str) -> list[str]:
    """Lexemas de la pregunta (stemming español) que existen en el índice y no son ubicuos.

    Filtro IDF: "trabaj", "dias", "año" aparecen en cientos de chunks y no ayudan a
    distinguir; con OR entre términos, dejarlos convierte la rama léxica en ruido.
    """
    await _load_doc_freq(session)
    cleaned = " ".join(re.findall(r"\w+", query_text.lower()))
    rows = (await session.execute(text("SELECT unnest(tsvector_to_array(to_tsvector('spanish', :q)))"), {"q": cleaned})).all()
    max_df = get_settings().lexical_max_df * _total_chunks
    return [r[0] for r in rows if 0 < _doc_freq.get(r[0], 0) <= max_df]


def _dedupe_by_article(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    out = []
    for chunk in chunks:
        if chunk.article_id not in seen:
            seen.add(chunk.article_id)
            out.append(chunk)
    return out


async def retrieve(
    session: AsyncSession,
    *,
    query_text: str,
    query_vector: list[float],
    search_mode: str = "vector",
    rerank: bool = False,
    top_k: int | None = None,
    recall_k: int | None = None,
    reranker: CrossEncoderReranker | None = None,
) -> tuple[list[RetrievedChunk], float]:
    """Devuelve (chunks de artículos distintos, latencia_ms)."""
    settings = get_settings()
    top_k = top_k or settings.rerank_top_n
    recall_k = recall_k or settings.retrieval_recall_k
    started = time.perf_counter()

    wide = rerank or search_mode == "hybrid"
    vector_rows = await _search_vector(session, query_vector, recall_k if wide else top_k * 3)
    lexical_rows = await _search_lexical(session, query_text, recall_k) if search_mode == "hybrid" else []

    candidates: dict[str, RetrievedChunk] = {}
    for row in vector_rows:
        candidates[row.chunk_id] = RetrievedChunk(
            row.chunk_id, row.article_id, row.content, row.embed_text, row.chunk_metadata,
            distance=float(row.distance), sources=["vector"],
        )
    for row in lexical_rows:
        if row.chunk_id in candidates:
            candidates[row.chunk_id].sources.append("lexical")
        else:
            candidates[row.chunk_id] = RetrievedChunk(
                row.chunk_id, row.article_id, row.content, row.embed_text, row.chunk_metadata, sources=["lexical"]
            )

    if search_mode == "hybrid":
        order = reciprocal_rank_fusion(
            [[r.chunk_id for r in vector_rows], [r.chunk_id for r in lexical_rows]],
            k=settings.rrf_k,
            weights=[1.0, settings.lexical_weight],
        )
    else:
        order = [r.chunk_id for r in vector_rows]
    ordered = [candidates[cid] for cid in order]

    if rerank and ordered:
        pool = ordered[:recall_k]
        scores = await asyncio.to_thread(
            (reranker or get_default_reranker()).score, query_text, [c.embed_text for c in pool]
        )
        for chunk, score in zip(pool, scores):
            chunk.rerank_score = score
        ordered = sorted(pool, key=lambda c: c.rerank_score, reverse=True)

    final = _dedupe_by_article(ordered)[:top_k]
    elapsed_ms = (time.perf_counter() - started) * 1000
    log_event(
        "retrieval_completed",
        search_mode=search_mode,
        rerank=rerank,
        vector_hits=len(vector_rows),
        lexical_hits=len(lexical_rows),
        results=len(final),
        latency_ms=round(elapsed_ms, 1),
    )
    return final, elapsed_ms
