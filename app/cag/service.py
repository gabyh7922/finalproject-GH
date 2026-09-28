"""Fase 1 — CAG (Cache-Augmented Generation): el Código completo en el contexto.

Igual que el estimador de las primeras sesiones: el conocimiento se inyecta
entero en el prompt, sin recuperación. El Código vigente ocupa ~258k tokens con
claude-opus-5, así que:

- Solo es viable en modelos de contexto largo (1M). En Haiku 4.5 (200k) no cabe.
- Sin caché, cada pregunta pagaría los 258k tokens de entrada (~US$1,3).
  Con prompt caching las preguntas siguientes leen el prefijo desde la
  caché a ~10% del precio. Aun así el costo por consulta es de un orden de
  magnitud mayor que el RAG, y la latencia también — por eso CAG queda como
  baseline de comparación, no como arquitectura de producción.

Ventaja real del CAG: el modelo "ve" todos los artículos, incluidas las
remisiones cruzadas ("conforme al artículo 161..."), que un retriever puede no
traer. Los evals comparan ambos enfoques con las mismas preguntas.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from xml.sax.saxutils import escape

from app.corpus import load_corpus, vigentes
from app.generation.citations import verify_citations
from app.generation.schemas import CitationReport, LegalAnswer
from app.llm import Usage, parse_structured
from app.prompts.loader import load_prompt


def render_article(article) -> str:
    return f'<articulo id="{article.article_id}">\n{escape(article.text)}\n</articulo>'


@lru_cache
def full_code_context() -> str:
    """Código completo, con la ruta jerárquica escrita solo cuando cambia.

    Primera versión repetía la ruta (Libro › Título › Capítulo) como atributo de
    cada artículo: 367k tokens en vez de ~260k. Escribirla una vez por sección
    conserva la estructura y ahorra ~30% del costo de cada consulta CAG.
    """
    meta = load_corpus()
    parts: list[str] = []
    current_path: tuple[str, ...] = ()
    for article in vigentes():
        if article.path != current_path:
            current_path = article.path
            parts.append(f"## {escape(article.breadcrumb)}")
        parts.append(render_article(article))
    body = "\n\n".join(parts)
    return (
        f"<codigo_del_trabajo version=\"{meta['fecha_version']}\" fuente=\"{meta['fuente']}\">\n"
        f"{body}\n</codigo_del_trabajo>"
    )


def build_system() -> list[dict]:
    # Instrucciones + Código completo forman un prefijo estable: la caché (TTL 5 min,
    # escritura a 1,25x; la de 1h cuesta 2x y no compensa para ráfagas de evals) lo
    # reutiliza entre preguntas. La pregunta va en el mensaje de usuario, DESPUÉS
    # del breakpoint, para no invalidarla.
    return [
        {"type": "text", "text": load_prompt("legal_answer")},
        {"type": "text", "text": full_code_context(), "cache_control": {"type": "ephemeral"}},
    ]


@dataclass
class CAGResult:
    request_id: str
    answer: LegalAnswer
    citation_report: CitationReport
    usage: Usage


def answer_question(question: str) -> CAGResult:
    request_id = str(uuid.uuid4())
    answer, usage = parse_structured(
        system=build_system(),
        user=f"Pregunta: {question}",
        output_format=LegalAnswer,
        request_id=request_id,
        stage="cag_answer",
    )
    context = {a.article_id: a.text for a in vigentes()}
    report = verify_citations(answer, context, request_id=request_id)
    return CAGResult(request_id=request_id, answer=answer, citation_report=report, usage=usage)
