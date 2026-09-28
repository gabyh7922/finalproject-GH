"""API de LexLaboral.

    GET  /health            estado + versión del corpus
    POST /search            recuperación sola (para inspeccionar el retriever)
    POST /ask               pregunta -> respuesta citada y verificada (mode: rag | cag)
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.corpus import articles_by_id, load_corpus
from app.database import get_db_session
from app.generation.schemas import LegalAnswer
from app.llm import RefusalError
from app.rag.embedder import embed_one
from app.rag.retrieval import retrieve

logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="LexLaboral", description="Asistente sobre el Código del Trabajo de Chile con citas verificables.")


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=5, ge=1, le=20)
    search_mode: Literal["vector", "hybrid"] = "vector"
    rerank: bool = True


class SearchHit(BaseModel):
    article_id: str
    label: str
    breadcrumb: str
    chunk_id: str
    content: str
    rerank_score: float | None
    found_by: list[str]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode: Literal["rag", "cag"] = "rag"


class CitationOut(BaseModel):
    article_id: str
    label: str
    status: str


class AskResponse(BaseModel):
    request_id: str
    mode: str
    answer: LegalAnswer
    citations: list[CitationOut]
    citation_precision: float
    retrieved_article_ids: list[str]
    cost_usd: float
    latency_ms: float
    corpus_version: str


@app.get("/health")
def health() -> dict:
    meta = load_corpus()
    return {"status": "ok", "corpus_version": meta["fecha_version"], "articles": meta["vigentes"]}


@app.post("/search", response_model=list[SearchHit])
async def search(req: SearchRequest, session: AsyncSession = Depends(get_db_session)):
    chunks, _ = await retrieve(
        session, query_text=req.query, query_vector=embed_one(req.query),
        search_mode=req.search_mode, rerank=req.rerank, top_k=req.k,
    )
    arts = articles_by_id()
    return [
        SearchHit(
            article_id=c.article_id, label=arts[c.article_id].label, breadcrumb=arts[c.article_id].breadcrumb,
            chunk_id=c.chunk_id, content=c.content, rerank_score=c.rerank_score, found_by=c.sources,
        )
        for c in chunks
    ]


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, session: AsyncSession = Depends(get_db_session)):
    try:
        if req.mode == "cag":
            from app.cag.service import answer_question as cag_answer

            result = cag_answer(req.question)
            retrieved_ids: list[str] = []
            latency = result.usage.latency_ms
        else:
            from app.generation.rag_pipeline import answer_question as rag_answer

            result = await rag_answer(session, req.question)
            retrieved_ids = [c.article_id for c in result.retrieved]
            latency = result.usage.latency_ms + result.retrieval_ms
    except RefusalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    arts = articles_by_id()
    return AskResponse(
        request_id=result.request_id,
        mode=req.mode,
        answer=result.answer,
        citations=[
            CitationOut(article_id=c.article_id, label=arts[c.article_id].label if c.article_id in arts else c.article_id, status=c.status)
            for c in result.citation_report.checks
        ],
        citation_precision=result.citation_report.citation_precision,
        retrieved_article_ids=retrieved_ids,
        cost_usd=round(result.usage.cost_usd, 5),
        latency_ms=round(latency, 1),
        corpus_version=load_corpus()["fecha_version"],
    )
