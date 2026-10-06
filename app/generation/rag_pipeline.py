"""Fase 4 — RAG completo: recuperación -> generación citada -> verificación de citas.

Mismo prompt (`legal_answer`) y mismo esquema de salida que el CAG: lo único
que cambia es el contexto. Así la comparación CAG vs RAG en los evals mide la
arquitectura, no diferencias de prompt.

"Small-to-big": se recupera por chunks (fragmentos pequeños, buenos para
buscar) pero al modelo se le entrega el **artículo completo** de cada chunk
recuperado (bueno para responder: un inciso suelto puede perder la regla o la
excepción que está en el inciso de al lado). Las citas se verifican contra ese
texto completo.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from xml.sax.saxutils import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.corpus import articles_by_id
from app.generation.citations import verify_citations
from app.generation.schemas import CitationReport, LegalAnswer
from app.llm import Usage, parse_structured
from app.prompts.loader import load_prompt
from app.rag.embedder import embed_one
from app.rag.retrieval import RetrievedChunk, retrieve


@dataclass
class RAGResult:
    request_id: str
    answer: LegalAnswer
    retrieved: list[RetrievedChunk]
    context: dict[str, str]  # article_id -> texto completo entregado al modelo
    citation_report: CitationReport
    usage: Usage
    retrieval_ms: float


def render_context(article_ids: list[str]) -> str:
    articles = articles_by_id()
    blocks = []
    for aid in article_ids:
        a = articles[aid]
        blocks.append(
            f'<articulo id="{a.article_id}" nombre="{escape(a.label)}" ubicacion="{escape(a.breadcrumb)}">\n'
            f"{escape(a.text)}\n</articulo>"
        )
    return "<articulos_recuperados>\n" + "\n\n".join(blocks) + "\n</articulos_recuperados>"


async def answer_question(
    session: AsyncSession,
    question: str,
    *,
    search_mode: str = "vector",
    rerank: bool = False,  # el reranker no mejoró la recuperación (evals/results/retrieval.md)
    top_k: int | None = None,
) -> RAGResult:
    request_id = str(uuid.uuid4())
    retrieved, retrieval_ms = await retrieve(
        session, query_text=question, query_vector=await asyncio.to_thread(embed_one, question),
        search_mode=search_mode, rerank=rerank, top_k=top_k,
    )
    article_ids = [c.article_id for c in retrieved]
    context = {aid: articles_by_id()[aid].text for aid in article_ids}

    # Las llamadas a OpenAI/Claude son bloqueantes: se ejecutan en un hilo para no
    # congelar el servidor (si no, el health check de Render falla y reinicia la instancia).
    answer, usage = await asyncio.to_thread(
        parse_structured,
        system=load_prompt("legal_answer"),
        user=f"{render_context(article_ids)}\n\nPregunta: {question}",
        output_format=LegalAnswer,
        request_id=request_id,
        stage="rag_answer",
    )
    report = verify_citations(answer, context, request_id=request_id)
    return RAGResult(request_id, answer, retrieved, context, report, usage, retrieval_ms)
