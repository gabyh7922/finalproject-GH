"""API + interfaz web de LexLaboral.

    GET  /                  interfaz web (app/static/index.html)
    GET  /health            estado, versión del corpus, gasto del día
    POST /search            recuperación sola (para inspeccionar el retriever)
    POST /ask               pregunta -> respuesta citada y verificada (mode: agent | rag | cag)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import guard
from app.config import get_settings
from app.corpus import articles_by_id, load_corpus
from app.database import get_db_session
from app.generation.schemas import LegalAnswer
from app.llm import RefusalError
from app.rag.embedder import embed_one
from app.rag.retrieval import retrieve

logging.basicConfig(level=logging.INFO, format="%(message)s")

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="LexLaboral", description="Asistente sobre el Código del Trabajo de Chile con citas verificables.")


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=5, ge=1, le=20)
    search_mode: Literal["vector", "hybrid"] = "vector"
    rerank: bool = False


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
    mode: Literal["agent", "rag", "cag"] = "agent"


class CitationOut(BaseModel):
    point: int
    article_id: str
    quote: str
    status: str


class ArticleOut(BaseModel):
    label: str
    breadcrumb: str
    text: str


class ToolCallOut(BaseModel):
    name: str
    input: dict
    is_error: bool


class AskResponse(BaseModel):
    request_id: str
    mode: str
    answer: LegalAnswer
    citations: list[CitationOut]
    citation_precision: float
    articles: dict[str, ArticleOut]
    consulted_article_ids: list[str]
    trace: list[ToolCallOut]
    cost_usd: float
    latency_ms: float
    corpus_version: str


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "?")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health() -> dict:
    meta = load_corpus()
    return {
        "status": "ok",
        "corpus_version": meta["fecha_version"],
        "articles": meta["vigentes"],
        "model": get_settings().llm_model,
        "spent_today_usd": guard.spent_today(),
    }


@app.post("/search", response_model=list[SearchHit])
async def search(req: SearchRequest, session: AsyncSession = Depends(get_db_session)):
    chunks, _ = await retrieve(
        session, query_text=req.query, query_vector=await asyncio.to_thread(embed_one, req.query),
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
async def ask(req: AskRequest, request: Request, session: AsyncSession = Depends(get_db_session)):
    if req.mode == "cag" and not get_settings().enable_cag:
        raise HTTPException(status_code=403, detail="El modo CAG está desactivado en la demo pública (cuesta ~US$1 por consulta).")
    blocked = guard.check(_client_ip(request))
    if blocked:
        raise HTTPException(status_code=429, detail=blocked)

    trace: list[ToolCallOut] = []
    try:
        if req.mode == "cag":
            from app.cag.service import answer_question as cag_answer

            result = await asyncio.to_thread(cag_answer, req.question)
            consulted: list[str] = []
            latency = result.usage.latency_ms
        elif req.mode == "rag":
            from app.generation.rag_pipeline import answer_question as rag_answer

            result = await rag_answer(session, req.question)
            consulted = [c.article_id for c in result.retrieved]
            latency = result.usage.latency_ms + result.retrieval_ms
        else:
            from app.agent.runner import run_agent

            result = await run_agent(session, req.question)
            consulted = result.seen_articles
            latency = result.usage.latency_ms + sum(t.latency_ms for t in result.trace)
            trace = [ToolCallOut(name=t.name, input=t.input, is_error=t.is_error) for t in result.trace]
    except RefusalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    guard.record_spend(result.usage.cost_usd)

    arts = articles_by_id()
    checks = iter(result.citation_report.checks)
    citations = []
    for i, point in enumerate(result.answer.points):
        for citation in point.citations:
            check = next(checks)
            citations.append(CitationOut(point=i, article_id=citation.article_id, quote=citation.quote, status=check.status))
    shown = {c.article_id for c in citations} | set(consulted)
    return AskResponse(
        request_id=result.request_id,
        mode=req.mode,
        answer=result.answer,
        citations=citations,
        citation_precision=result.citation_report.citation_precision,
        articles={
            aid: ArticleOut(label=arts[aid].label, breadcrumb=arts[aid].breadcrumb, text=arts[aid].text)
            for aid in shown if aid in arts
        },
        consulted_article_ids=consulted,
        trace=trace,
        cost_usd=round(result.usage.cost_usd, 5),
        latency_ms=round(latency, 1),
        corpus_version=load_corpus()["fecha_version"],
    )
